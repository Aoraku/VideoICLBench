"""Example image-only OpenAI-compatible policy; credentials via environment only.
Use only with a provider/model accepting image content and JSON response format.
Full-video conditions need a native-video policy; this adapter refuses them.
"""
import json
import os
import sys
import httpx

def main():
    messages=[dict(role='system',content='You control two Panda arms through camera images. Infer the task from the demonstration. Output only JSON with left, right action tokens and submit boolean. No simulator tools or state are available.')]
    with httpx.Client(timeout=110) as c:
        for line in sys.stdin:
            payload=json.loads(line); content=[]; demo=payload.get('demonstration')
            if demo:
                if 'video' in demo: raise ValueError('This adapter supports frames, text and no_demo only; use a native-video policy for video conditions')
                if 'instruction' in demo: content.append(dict(type='text',text=demo['instruction']))
                if 'frames' in demo:
                    content.append(dict(type='text',text='Demonstration: 16 frames in chronological order.'))
                    for f in demo['frames']: content.append(dict(type='image_url',image_url=dict(url='data:image/jpeg;base64,'+f)))
            obs=payload['observation']
            content.append(dict(type='text',text=payload['interface']+' Allowed tokens: '+','.join(payload['actions'])+f" Remaining actions: {obs['remaining']}."))
            for camera,img in obs['images'].items():
                content.extend([dict(type='text',text=camera),dict(type='image_url',image_url=dict(url='data:image/jpeg;base64,'+img))])
            messages.append(dict(role='user',content=content))
            r=c.post(os.environ['POLICY_BASE_URL'].rstrip('/')+'/chat/completions',
                headers={'Authorization':'Bearer '+os.environ['POLICY_API_KEY']},
                json=dict(model=os.environ['POLICY_MODEL'],messages=messages,response_format={'type':'json_object'}))
            r.raise_for_status(); reply=r.json()['choices'][0]['message']['content'];decision=json.loads(reply)
            messages.append(dict(role='assistant',content=json.dumps(decision)))
            # Keep demo and latest images; historical images otherwise grow quadratically.
            if len(messages)>8: messages=[messages[0],messages[1]]+messages[-4:]
            print(json.dumps(decision),flush=True)
if __name__=='__main__': main()
