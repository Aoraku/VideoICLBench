"""Measured settling compensation for private engineering reference authors.

This only chooses public action magnitudes from achieved physical rotations.
It does not change controls, targets, poses, scores or success tolerances.
"""
import math
import numpy as np


def command_degrees(component_error_rad,estimated_loss_degrees=0.,maximum=8.):
    return min(float(maximum),max(.5,abs(math.degrees(component_error_rad))+float(estimated_loss_degrees)))


def update_loss(before,after,component,direction,requested_degrees,previous_loss):
    achieved=np.asarray(after,float)@np.asarray(before,float).T
    angle=float(np.arccos(np.clip((np.trace(achieved)-1)/2,-1,1)))
    if angle>1e-7 and math.pi-angle>.01:
        axis=np.array([achieved[2,1]-achieved[1,2],achieved[0,2]-achieved[2,0],achieved[1,0]-achieved[0,1]])/(2*math.sin(angle))
        actual=math.degrees(angle*axis[int(component)])*np.sign(direction)
    else:actual=0.
    measured=float(np.clip(float(requested_degrees)-actual,0.,7.8))
    return .5*float(previous_loss)+.5*measured,float(actual)
