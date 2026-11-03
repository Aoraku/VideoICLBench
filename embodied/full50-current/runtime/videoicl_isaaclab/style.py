"""Bright, stable identity colors; neutral targets never encode a hidden rule."""
import math
PALETTE={'red':'F04452','green':'24BD79','blue':'3478F6','yellow':'F9C83D','purple':'A85CE5','white':'E9EDF2'}
REFERENCE={'red':(.85,.12,.1),'green':(.12,.7,.22),'blue':(.12,.3,.85),'yellow':(.95,.72,.12),'purple':(.65,.2,.75),'white':(.85,.85,.85)}

def rgb(hexcode):return tuple(int(hexcode[i:i+2],16)/255 for i in (0,2,4))
def linear(rgb):return tuple(x/12.92 if x<=.04045 else ((x+.055)/1.055)**2.4 for x in rgb)
def color(rgba):
    key=min(REFERENCE,key=lambda k:sum((a-b)**2 for a,b in zip(rgba[:3],REFERENCE[k])))
    return linear(rgb(PALETTE[key]))
TABLE=linear(rgb('F1EDE3'))
FRAME=linear(rgb('253649'))
PAD=linear(rgb('D2DFE5'))
MARKER=linear(rgb('304559'))

def marker_points(xy,index,radius,z,yaw=0.):
    # 0=circle, 1=triangle, 2=square, 3=cross. Cross endpoints are two
    # separate diagonals; the other markers are closed outlines.
    if index==3:
        d=radius/math.sqrt(2)
        c,s=math.cos(yaw),math.sin(yaw)
        return [(xy[0]+c*dx-s*dy,xy[1]+s*dx+c*dy,z) for dx,dy in ((-d,-d),(d,d),(-d,d),(d,-d))]
    n=(48,3,4)[index]
    # Same mark orientation across seeds and variants.
    return [(xy[0]+radius*math.cos(2*math.pi*i/n+yaw),xy[1]+radius*math.sin(2*math.pi*i/n+yaw),z) for i in range(n)]
