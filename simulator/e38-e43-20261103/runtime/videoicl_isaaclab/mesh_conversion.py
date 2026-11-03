"""Bake static GLB node transforms for URDF importers that discard them.

Preserves embedded images, materials, primitive indices and original source bytes.
Only POSITION/NORMAL/TANGENT accessors in the conversion copy are replaced.
"""
import copy,json,struct
from pathlib import Path
import numpy as np
from .layout import rotation_matrix


def bake_glb(source,target):
    raw=Path(source).read_bytes()
    magic,version,total=struct.unpack_from('<III',raw)
    if magic!=0x46546c67 or version!=2 or total!=len(raw):raise ValueError('Expected GLB 2')
    offset=12;document=None;blob=None
    while offset<len(raw):
        length,kind=struct.unpack_from('<II',raw,offset);offset+=8
        chunk=raw[offset:offset+length];offset+=length
        if kind==0x4e4f534a:document=json.loads(chunk)
        elif kind==0x004e4942:blob=bytearray(chunk)
    if document is None or blob is None or len(document['buffers'])!=1:raise ValueError('Expected embedded single-buffer GLB')
    original_meshes=copy.deepcopy(document['meshes']);original_nodes=copy.deepcopy(document['nodes'])
    document['meshes']=[]
    def read_accessor(index):
        a=document['accessors'][index];view=document['bufferViews'][a['bufferView']]
        if a['componentType']!=5126 or 'sparse' in a:raise ValueError('Expected dense float vertex attributes')
        dims={'VEC3':3,'VEC4':4}[a['type']]
        stride=view.get('byteStride',dims*4);begin=view.get('byteOffset',0)+a.get('byteOffset',0)
        return np.ndarray((a['count'],dims),dtype='<f4',buffer=blob,offset=begin,strides=(stride,4)).copy()
    def write_accessor(original,values):
        values=np.asarray(values,dtype='<f4');a=copy.deepcopy(document['accessors'][original])
        while len(blob)%4:blob.append(0)
        start=len(blob);blob.extend(values.tobytes())
        view=dict(buffer=0,byteOffset=start,byteLength=values.nbytes,target=34962)
        document['bufferViews'].append(view);a['bufferView']=len(document['bufferViews'])-1
        a['byteOffset']=0;a.pop('sparse',None)
        a['min']=values.min(axis=0).astype(float).tolist();a['max']=values.max(axis=0).astype(float).tolist()
        document['accessors'].append(a);return len(document['accessors'])-1
    seen=set();baked=0
    def visit(index,parent):
        nonlocal baked
        if index in seen:raise ValueError('GLB node is instanced in multiple parents')
        seen.add(index);node=original_nodes[index]
        if 'matrix' in node:local=np.array(node['matrix']).reshape(4,4,order='F')
        else:
            local=np.eye(4);x,y,z,w=node.get('rotation',[0,0,0,1])
            local[:3,:3]=rotation_matrix([w,x,y,z])@np.diag(node.get('scale',[1,1,1]))
            local[:3,3]=node.get('translation',[0,0,0])
        world=parent@local
        if np.linalg.det(world[:3,:3])<=0:raise ValueError('Reflected/singular GLB requires explicit winding adaptation')
        if 'mesh' in node:
            mesh=copy.deepcopy(original_meshes[node['mesh']])
            for primitive in mesh['primitives']:
                if 'targets' in primitive:raise ValueError('Animated GLB cannot be baked as static URDF mesh')
                for key in ('POSITION','NORMAL','TANGENT'):
                    if key not in primitive['attributes']:continue
                    accessor=primitive['attributes'][key];values=read_accessor(accessor)
                    if key=='POSITION':values=values@world[:3,:3].T+world[:3,3]
                    else:
                        vectors=values[:,:3]@(np.linalg.inv(world[:3,:3]) if key=='NORMAL' else world[:3,:3].T)
                        vectors/=np.maximum(np.linalg.norm(vectors,axis=1,keepdims=True),1e-15)
                        values[:,:3]=vectors
                    primitive['attributes'][key]=write_accessor(accessor,values)
            document['meshes'].append(mesh);document['nodes'][index]['mesh']=len(document['meshes'])-1;baked+=1
        for key in ('matrix','translation','rotation','scale'):document['nodes'][index].pop(key,None)
        for child in node.get('children',[]):visit(child,world)
    if document.get('animations') or document.get('skins'):raise ValueError('Animated/skinned mesh is not a static URDF visual')
    for index in document['scenes'][document.get('scene',0)]['nodes']:visit(index,np.eye(4))
    document['buffers'][0]['byteLength']=len(blob)
    text=json.dumps(document,separators=(',',':')).encode()
    text+=b' '*((-len(text))%4);blob.extend(b'\0'*((-len(blob))%4))
    output=struct.pack('<III',magic,version,12+8+len(text)+8+len(blob))+struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(blob),0x004e4942)+bytes(blob)
    Path(target).write_bytes(output)
    return dict(mesh_nodes_baked=baked,source_bytes=len(raw),converted_bytes=len(output))
