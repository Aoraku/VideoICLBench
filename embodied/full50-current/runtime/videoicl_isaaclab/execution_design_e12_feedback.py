"""Measured public-action prediction for E12 engineering pin insertion only."""
from types import SimpleNamespace
import numpy as np
from scipy.spatial.transform import Rotation
from .realworld_tool_expert import ToolExecutionError


class PinResponse:
    def __init__(self,author,name,slot,side):
        self.author=author;self.name=name;self.slot=slot;self.side=side;self.samples={};self.last_token=None

    @staticmethod
    def response_key(token,previous):
        if token!='STILL':return token
        if previous not in ('FWD','BACK','LEFT','RIGHT','DOWN'):
            raise ToolExecutionError('E12 STILL requires immediately preceding calibrated public translation')
        return 'STILL'if previous=='DOWN'else 'STILL_AFTER_'+previous

    def act(self,token):
        key=self.response_key(token,self.last_token)
        a=self.author;p0,r0=a.frame({'actor':self.name})
        a.act(self.side,token,mm=.5)
        p1,r1=a.frame({'actor':self.name})
        sample=np.r_[np.asarray(p1)-p0,Rotation.from_matrix(np.asarray(r1)@np.asarray(r0).T).as_rotvec()]
        if not np.isfinite(sample).all():raise ToolExecutionError('E12 nonfinite actual public-action response')
        self.samples.setdefault(key,[]).append(sample)
        self.samples[key]=self.samples[key][-4:]
        self.last_token=token
        report=getattr(getattr(a,'a',None),'control_report',None)
        if isinstance(report,dict):report['e12_active_pin_response']=dict(actor=self.name,slot=self.slot,side=self.side,
            last_token=self.last_token,samples={k:[value.tolist()for value in values]for k,values in self.samples.items()})

    def response(self,token):
        samples=self.samples.get(token,[])
        if len(samples)<2:return None
        values=np.asarray(samples);mean=np.median(values,axis=0)
        # No extrapolation from inconsistent tracking or a contact-induced stall.
        if np.max(np.linalg.norm(values[:,:3]-mean[:3],axis=1))>.00015:return None
        if np.max(np.linalg.norm(values[:,3:]-mean[3:],axis=1))>np.radians(.15):return None
        return mean

    def path_margin(self,tokens):
        from .execution_design_e12_reference import insertion_channel_diagnostics,pin_aperture_diagnostics
        # A public hold is usable only in its actual calibrated prior-motion context.
        a=self.author;p,r=a.frame({'actor':self.name});p=np.asarray(p).copy();r=np.asarray(r).copy();margin=float('inf');uncertainty=0.;previous=self.last_token
        channel=bool(getattr(a,'_e12_toe_preparation',{}).get('replanned_source_toe28'))
        for token in tokens:
            try:key=self.response_key(token,previous)
            except ToolExecutionError:return None
            response=self.response(key)
            if response is None:return None
            values=np.asarray(self.samples[key]);translation_error=float(np.max(np.linalg.norm(values[:,:3]-response[:3],axis=1)))
            rotation_error=float(np.max(np.linalg.norm(values[:,3:]-response[3:],axis=1)))
            # Reserve observed repeatability plus 10um for gradual response drift.
            # Native v11 crossed the unchanged50um real guard by0.82um.
            # Bound rotation at every pin point with its actual object lever arm.
            lever=max(np.linalg.norm(pin['tip_local'])+float(pin['length'])for pin in a.s['pins'][self.name])
            prior_uncertainty=uncertainty
            increment=translation_error+lever*rotation_error+.00001
            uncertainty+=increment
            for fraction in np.linspace(0,1,9):
                position=p+response[:3]*fraction;rotation=Rotation.from_rotvec(response[3:]*fraction).as_matrix()@r
                view=SimpleNamespace(s=a.s)
                view.frame=lambda ref,position=position,rotation=rotation:(position,rotation)if ref.get('actor')==self.name else a.frame(ref)
                view.body_point=lambda ref,point:view.frame(ref)[0]+view.frame(ref)[1]@np.asarray(point)
                rows=(insertion_channel_diagnostics if channel else pin_aperture_diagnostics)(view,self.name,self.slot)
                if not all(row['fits']for row in rows):return None
                occupied=[min(row['margin_m'])for row in rows if row['margin_m']is not None]
                if not occupied:continue
                measured_margin=min(occupied)
                bound=prior_uncertainty+increment*fraction
                if measured_margin<.00005+bound:return None
                margin=min(margin,measured_margin-bound)
            p=p+response[:3];r=Rotation.from_rotvec(response[3:]).as_matrix()@r
            previous=token
        return margin

    def choose(self):
        down=self.path_margin(['DOWN'])
        if (getattr(self.author,'_e12_single_step_reference',False)
                or getattr(self.author,'_e12_toe_preparation',{}).get('replanned_source_toe28')):
            # Reobserve the real pins after each action. Multi-step accumulated
            # envelopes remain useful diagnostics, not a gate on a safe step.
            if down is not None:return 'DOWN'
            candidates=[]
            for token in('FWD','BACK','LEFT','RIGHT','STILL'):
                margin=self.path_margin([token])
                if margin is not None:candidates.append((margin,token))
            if candidates:return max(candidates)[1]
            raise ToolExecutionError('E12 no measured safe single public action through both apertures')
        from itertools import product
        if down is not None:
            # Do not greedily descend into a discrete-action corner with no
            # measured continuation. At most two public corrections look ahead.
            for count in range(3):
                if any(self.path_margin(['DOWN',*prefix,'DOWN'])is not None
                       for prefix in product(('FWD','BACK','LEFT','RIGHT','STILL'),repeat=count)):
                    return 'DOWN'
        # Native560 had already inserted both pins3.7mm with82um clearance.
        # A safe FWD existed but required LEFT before the next DOWN. Search a
        # bounded sequence; every segment uses measured responses and the same
        # full dual-pin aperture sweep. Reobserve after its first public action.
        from itertools import product
        choices=[]
        for count in range(1,4):
            for prefix in product(('FWD','BACK','LEFT','RIGHT','STILL'),repeat=count):
                margin=self.path_margin([*prefix,'DOWN'])
                if margin is not None:choices.append((margin,-count,prefix[0]))
        if not choices:raise ToolExecutionError('E12 no measured safe public action through both apertures')
        return max(choices)[2]
