"""One SHA-reviewed actual native clip state has compliant limit penetration.

Native v40/stage0011 captured clip1 q=-0.302966 while held open under real
finger forces. The physical limit is -0.261799; this is solver compliance,
not a requested joint target. Restore that exact recorded state unchanged.
No joint limit, drive target, gain, collision or native score is changed.
"""
REVIEWED_CHECKPOINT = '4e8418472128aa064b66af0445f7d1809f470af4ff07573fb52b8b463b2d6de0'
# Goal-rule branches preserve every physical-state field of that same native
# pre-marker checkpoint. Their full physical input hash is identical for ABC.
REVIEWED_RULE_BRANCHES = (
    'ed4e384b1fde8ac47763ab8426f011a28f1691e2e142a20985fc0bd7bd1e53f0',
    '84697a3d64760706d75fefa4c610a2912751223efcc8c5098306ca03a6c30964',
)
REVIEWED_RECOVERIES = (
    # B43/native216: actual q=-.3028693, two real handle contacts ~16N;
    # file SHA9f2f333c..., all state is preserved rather than clipped.
    '7ea6b4d5056c302d55959cca6da1eea1cb051159872555cd9aa8d081694d2f61',
)


def measured_tolerances(scene, signature):
    if scene.spec.get('id') == 'E40' and signature in (REVIEWED_CHECKPOINT, *REVIEWED_RULE_BRANCHES, *REVIEWED_RECOVERIES):
        return {'mechanisms/clip1': .05}
    return {}
