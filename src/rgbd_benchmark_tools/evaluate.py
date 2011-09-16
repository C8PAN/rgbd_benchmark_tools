#!/usr/bin/python
#
# Requirements: 
# sudo apt-get install python-argparse

import argparse
import sys
import os
import numpy
import random

_EPS = numpy.finfo(float).eps * 4.0

def transform44(l):
    t = l[1:4]
    q = numpy.array(l[4:8], dtype=numpy.float64, copy=True)
    nq = numpy.dot(q, q)
    if nq < _EPS:
        return numpy.array((
        (                1.0,                 0.0,                 0.0, t[0])
        (                0.0,                 1.0,                 0.0, t[1])
        (                0.0,                 0.0,                 1.0, t[2])
        (                0.0,                 0.0,                 0.0, 1.0)
        ), dtype=numpy.float64)
    q *= numpy.sqrt(2.0 / nq)
    q = numpy.outer(q, q)
    return numpy.array((
        (1.0-q[1, 1]-q[2, 2],     q[0, 1]-q[2, 3],     q[0, 2]+q[1, 3], t[0]),
        (    q[0, 1]+q[2, 3], 1.0-q[0, 0]-q[2, 2],     q[1, 2]-q[0, 3], t[1]),
        (    q[0, 2]-q[1, 3],     q[1, 2]+q[0, 3], 1.0-q[0, 0]-q[1, 1], t[2]),
        (                0.0,                 0.0,                 0.0, 1.0)
        ), dtype=numpy.float64)

def read_trajectory(filename):
    file = open(filename)
    data = file.read()
    lines = data.replace(","," ").replace("\t"," ").split("\n") 
    list = [[float(v.strip()) for v in line.split(" ") if v.strip()!=""] for line in lines if len(line)>0 and line[0]!="#"]
    list_ok = []
    for i,l in enumerate(list):
        if l[4:8]==[0,0,0,0]:
            continue
        isnan = False
        for v in l:
            if numpy.isnan(v): 
                isnan = True
                break
        if isnan:
            sys.stderr.write("Warning: line %d of file '%s' has NaNs, skipping line"%(i,filename))
            continue
        list_ok.append(l)
    traj = dict([(l[0],transform44(l[0:])) for l in list_ok])
    return traj

def find_closest_index(L,t):
    beginning = 0
    difference = abs(L[0] - t)
    best = 0
    end = len(L)
    while beginning < end:
        middle = int((end+beginning)/2)
        if abs(L[middle] - t) < difference:
            difference = abs(L[middle] - t)
            best = middle
        if t == L[middle]:
            return middle
        elif L[middle] > t:
            end = middle
        else:
            beginning = middle + 1
    return best

def ominus(a,b):
    return numpy.dot(numpy.linalg.inv(a),b)

def compute_distance(transform):
    return numpy.linalg.norm(transform[0:3,3])

def compute_angle(transform):
    # an invitation to 3-d vision, p 27
    return numpy.arccos( min(1,max(-1, (numpy.trace(transform[0:3,0:3]) - 1)/2) ))

def distances_along_trajectory(traj):
    keys = traj.keys()
    keys.sort()
    motion = [ominus(traj[keys[i+1]],traj[keys[i]]) for i in range(len(keys)-1)]
    distances = [0]
    sum = 0
    for t in motion:
        sum += compute_distance(t)
        distances.append(sum)
    return distances
    
def rotations_along_trajectory(traj):
    keys = traj.keys()
    keys.sort()
    motion = [ominus(traj[keys[i+1]],traj[keys[i]]) for i in range(len(keys)-1)]
    distances = [0]
    sum = 0
    for t in motion:
        sum += compute_angle(t)
        distances.append(sum)
    return distances
    

def evaluate_trajectory(traj_gt,traj_est,param_max_pairs=10000,param_fixed_delta=False,param_delta=1.00,param_delta_unit="s",param_offset=0.00):
    stamps_gt = list(traj_gt.keys())
    stamps_est = list(traj_est.keys())
    stamps_gt.sort()
    stamps_est.sort()
    
    stamps_est_return = []
    for t_est in stamps_est:
        t_gt = stamps_gt[find_closest_index(stamps_gt,t_est - param_offset)]
        t_est_return = stamps_est[find_closest_index(stamps_est,t_gt + param_offset)]
        t_gt_return = stamps_gt[find_closest_index(stamps_gt,t_est_return - param_offset)]
        if not t_est_return in stamps_est_return:
            stamps_est_return.append(t_est_return)
    if(len(stamps_est_return)<2):
        raise Exception("Number of overlap in the timestamps is too small. Did you run the evaluation on the right files?")

    if param_delta_unit=="s":
        index_est = list(traj_est.keys())
        index_est.sort()
    elif param_delta_unit=="m":
        index_est = distances_along_trajectory(traj_est)
    elif param_delta_unit=="rad":
        index_est = rotations_along_trajectory(traj_est)
    elif param_delta_unit=="f":
        index_est = range(len(traj_est))
    else:
        raise Exception("Unknown unit for delta: '%s'"%param_delta_unit)

    if not param_fixed_delta:
        if(param_max_pairs==0 or len(traj_est)<numpy.sqrt(param_max_pairs)):
            pairs = [(i,j) for i in range(len(traj_est)) for j in range(len(traj_est))]
        else:
            pairs = [(random.randint(0,len(traj_est)-1),random.randint(0,len(traj_est)-1)) for i in range(param_max_pairs)]
    else:
        pairs = []
        for i in range(len(traj_est)):
            j = find_closest_index(index_est,index_est[i] + param_delta)
            if j!=len(traj_est)-1: 
                pairs.append((i,j))
        if(param_max_pairs!=0 and len(pairs)>param_max_pairs):
            pairs = random.sample(pairs,param_max_pairs)
    
    gt_interval = numpy.median([s-t for s,t in zip(stamps_gt[1:],stamps_gt[:-1])])
    gt_max_time_difference = 2*gt_interval
    
    result = []
    for i,j in pairs:
        stamp_est_0 = stamps_est[i]
        stamp_est_1 = stamps_est[j]

        stamp_gt_0 = stamps_gt[ find_closest_index(stamps_gt,stamp_est_0 - param_offset) ]
        stamp_gt_1 = stamps_gt[ find_closest_index(stamps_gt,stamp_est_1 - param_offset) ]
        
        if(abs(stamp_gt_0 - (stamp_est_0 - param_offset)) > gt_max_time_difference  or
           abs(stamp_gt_1 - (stamp_est_1 - param_offset)) > gt_max_time_difference):
            continue
        
        error44 = ominus(  ominus( traj_est[stamp_est_1], traj_est[stamp_est_0] ),
                           ominus( traj_gt[stamp_gt_1], traj_gt[stamp_gt_0] ) )
        
        trans = compute_distance(error44)
        rot = compute_angle(error44)
        
        result.append([stamp_est_0,stamp_est_1,stamp_gt_0,stamp_gt_1,trans,rot])
        
    if len(result)<2:
        raise Exception("Couldn't find matching timestamp pairs between groundtruth and estimated trajectory!")
        
    return result

if __name__ == '__main__':
    random.seed(0)

    parser = argparse.ArgumentParser(description='''
    This script reads a ground-truth trajectory and an estimated trajectory, and computes -- by default -- the root mean squared translational error.
    ''')
    parser.add_argument('groundtruth_file', help='ground-truth trajectory file (format: "timestamp tx ty tz qx qy qz qw")')
    parser.add_argument('estimated_file', help='estimated trajectory file (format: "timestamp tx ty tz qx qy qz qw")')
    parser.add_argument('--max_pairs', help='maximum number of pose comparisons (default: 10000, set to zero to disable downsampling)', default=10000)
    parser.add_argument('--fixed_delta', help='only consider pose pairs that have a distance of delta delta_unit (e.g., for evaluating the drift per second/meter/radian)', action='store_true')
    parser.add_argument('--delta', help='delta for evaluation (default: 1.0)',default=1.0)
    parser.add_argument('--delta_unit', help='unit of delta (options: \'s\' for seconds, \'m\' for meters, \'rad\' for radians, \'f\' for frames; default: \'s\')',default='s')
    parser.add_argument('--offset', help='time offset between ground-truth and estimated trajectory (default: 0.0)',default=0.0)
    parser.add_argument('--save', help='text file to which the evaluation will be saved (format: stamp_est0 stamp_est1 stamp_gt0 stamp_gt1 trans_error rot_error)')
    parser.add_argument('--verbose', help='print all evaluation data (otherwise, only the mean translational error measured in meters will be printed)', action='store_true')
    args = parser.parse_args()
    
    traj_gt = read_trajectory(args.groundtruth_file)
    traj_est = read_trajectory(args.estimated_file)
    
    result = evaluate_trajectory(traj_gt,
                                 traj_est,
                                 int(args.max_pairs),
                                 args.fixed_delta,
                                 float(args.delta),
                                 args.delta_unit,
                                 float(args.offset))
    
    trans_error = numpy.array(result)[:,4]
    rot_error = numpy.array(result)[:,5]
    
    if args.save:
        f = open(args.save,"w")
        f.write("\n".join([" ".join(["%f"%v for v in line]) for line in result]))
        f.close()
    
    if args.verbose:
        print "compared_pose_pairs %d pairs"%(len(trans_error))

        print "translational_error.rmse %f m"%numpy.sqrt(numpy.dot(trans_error,trans_error) / len(trans_error))
        print "translational_error.mean %f m"%numpy.mean(trans_error)
        print "translational_error.median %f m"%numpy.median(trans_error)
        print "translational_error.std %f m"%numpy.std(trans_error)
        print "translational_error.min %f m"%numpy.min(trans_error)
        print "translational_error.max %f m"%numpy.max(trans_error)

        print "rotational_error.rmse %f deg"%(numpy.sqrt(numpy.dot(rot_error,rot_error) / len(rot_error)) * 180.0 / numpy.pi)
        print "rotational_error.mean %f deg"%(numpy.mean(rot_error) * 180.0 / numpy.pi)
        print "rotational_error.median %f deg"%numpy.median(rot_error)
        print "rotational_error.std %f deg"%(numpy.std(rot_error) * 180.0 / numpy.pi)
        print "rotational_error.min %f deg"%(numpy.min(rot_error) * 180.0 / numpy.pi)
        print "rotational_error.max %f deg"%(numpy.max(rot_error) * 180.0 / numpy.pi)
    else:
        print numpy.sqrt(numpy.dot(trans_error,trans_error) / len(trans_error))
