"""Alternative lossless rendering of the frozen public depth projection for two CLI pilots."""
from copy import deepcopy
import json

# Keep the frame, coordinates, calibration reference, validity, precision and pixel
# values directly on each measurement. Only shared descriptive metadata can move.
DESCRIPTORS = ('camera','depth_convention','estimated','height','width','measurement_source',
               'method','observation_tick','physical_action','pixel_order','pixel_space',
               'projection_source','rgb_sha256','sampling','sensor_source','surface_note',
               'target_frame','units')
CONTRACT = 'Each measurement inherits the shared_measurement_metadata on its enclosing result. All sampled pixels, values and coordinate frames are unchanged.'

def wire(data):
    return json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False)

def pack(public):
    result=deepcopy(public)
    changed=False
    for rec in result.get('results',[]):
        points=rec.get('measurements')
        if not isinstance(points,list) or len(points)<2 or not all(isinstance(p,dict) for p in points):continue
        if 'shared_measurement_metadata' in rec:continue
        first=points[0]
        common={k:first[k] for k in DESCRIPTORS if k in first and all(k in p and wire(first[k])==wire(p[k]) for p in points[1:])}
        if not common:continue
        rec['shared_measurement_metadata']=common
        for p in points:
            for k in common:del p[k]
        changed=True
    if changed:
        result['measurement_metadata_contract']=CONTRACT
    return result if len(wire(result))<len(wire(public)) else public

def unpack(public):
    result=deepcopy(public)
    if result.get('measurement_metadata_contract')!=CONTRACT:return result
    del result['measurement_metadata_contract']
    for rec in result.get('results',[]):
        common=rec.pop('shared_measurement_metadata',{})
        for p in rec.get('measurements',[]):
            if p.keys()&common.keys():raise ValueError('Overlapping shared metadata')
            p.update(common)
    return result

def install(reference_cls,reference_factory):
    from mcp.types import CallToolResult, TextContent
    from vic_sdk.robodawn_turn_context import _model_measurement_projection

    class Tools(reference_cls):
        def result(self,saved,*,include_images=True):
            original=super().result(saved,include_images=include_images)
            if saved.get('kind')!='depth_points' or not original.content:return original
            block=original.content[0]
            if block.type!='text':return original
            baseline=json.loads(block.text)
            if original.isError:
                if baseline.get('error')!='public_result_too_large':return original
                # Recover only the frozen public projection. Never forward internal raw measurements.
                if saved.get('observation') or saved.get('images'):return original
                baseline=deepcopy(saved)
                baseline.pop('images',None)
                cal={}
                baseline['results']=_model_measurement_projection(baseline['results'],cal)
                if cal:
                    baseline['measurement_calibrations']=cal
                    baseline['calibration_reference_contract']='calibration_ref resolves to this packet measurement_calibrations; exact frame/camera'
                baseline['truncated']=False
                baseline['history_event_count']=len(self.state['events'])
            packed=pack(baseline)
            if unpack(packed)!=baseline:raise ValueError('Lossy public depth encoding')
            text=wire(packed)
            if len(text.encode())>24000:
                if not original.isError:return original
                error=json.loads(block.text)
                error['message']='The public depth result exceeds the response limit. Request fewer pixel coordinates in this depth query. No physical action was executed.'
                return CallToolResult(isError=True,content=[TextContent(type='text',text=wire(error))])
            return CallToolResult(content=[TextContent(type='text',text=text),*original.content[1:]])

    def make_server(backend):
        server=reference_factory(backend)
        tool=server._tool_manager.get_tool('depth_points')
        if tool is None or '1..16' not in tool.description:raise ValueError('Unrecognized frozen depth schema')
        tool.description='Read public native-camera depth at your selected [row,col] pixels. Supply 1 to 16 coordinates. There is no default grid. All measurements use the displayed frame; matching calibration and coordinates are included.'
        return server
    return Tools,make_server
