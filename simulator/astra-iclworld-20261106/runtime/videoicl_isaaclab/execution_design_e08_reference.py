"""E08-only engineering material feedback; source task and grasp truth unchanged."""
from .realworld_structural_expert import StructuralAuthor
from .execution_design_tool_tracking import move_material


class MeasuredShoeAuthor(StructuralAuthor):
    def move_point(self,side,ref,target,guard=None,follower=None,tolerance=.002):
        # Every public action gets fresh shoe geometry, including slip under
        # gravity. Arrival uses the original material-point tolerance.
        return move_material(self,side,ref,target,guard,follower,tolerance)


def solve_e08_reference(author):
    spec=author.scene.spec
    if (spec.get('id')!='E08' or spec.get('execution_design',{}).get('revision')!='embodied50-execution-v3-20261102'
            or not author.control_report.get('engineering_reference_only') or spec.get('author_smooth_recording',False)):
        raise ValueError('E08 v3 public-action engineering reference required')
    from .execution_design_e08_source_pair import solve
    return solve(author)
