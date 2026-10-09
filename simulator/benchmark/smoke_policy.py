"""Protocol check only: one upward move and submit, deliberately no task solver."""
import json
import sys
for i,line in enumerate(sys.stdin):
    json.loads(line)
    print(json.dumps(dict(left='UP' if i==0 else 'STILL',right='STILL',submit=i>0)),flush=True)
