"""Public episode semantics, shared across conditions; no task-specific hints."""

EPISODE_CONTRACT_VERSION = 'videoicl-simulator-depth-only-episode-memory-v7'
TERMINATION_INSTRUCTIONS = (
    'Done ends the episode and declares that you believe the requested task is complete. '
    'Use Done only after examining the latest returned GUI observation and judging that all requested goals are satisfied. '
    'A successful tool call or partial progress alone does not mean the task is complete. '
    'Give up ends the episode without claiming success. Use Give up only when you judge from the observed task state '
    'that the task cannot be completed. '
    'For either terminal tool, pass the frame_id from the latest GUI observation you actually received. '
    'These are your task judgments; pressing a terminal button does not certify success.')
WAIT_INSTRUCTIONS = (
    'An accepted GUI operation may take time while infrastructure completes it. Pending is not task failure. '
    'Wait for the original operation to finish and return its new GUI observation before making another decision. '
    'Do not cancel an accepted operation, duplicate its inputs, reset the session, or replay earlier actions. '
    'Slow responses, pending operations, temporary API failures, and infrastructure waiting are not reasons to use Done or Give up. '
    'If a call was interrupted, obtain a fresh GUI observation after the controller reconnects before deciding what to do.')
GUI_BATCH_INSTRUCTIONS = (
    'You can prepare one robot action in a single act call containing multiple GUI inputs: '
    'select the left and right arm buttons, edit the distance or angle if needed, then click Commit once. '
    'Changing selections or editing fields does not move the robot; Commit executes both selected arms together. '
    'Selecting another button for the same arm replaces its selection; it does not queue multiple motions. '
    'Batch the edits you can decide from the current screenshot instead of requesting a separate observation after each edit. '
    'An act call returns the updated GUI, so use that returned frame for the next decision. '
    'Use at most one physical Commit in each act call and inspect its returned feedback before the next Commit.')
DEPTH_SENSOR_INSTRUCTIONS = (
    'Read the observation sensor mode and provenance before using depth. '
    'Public observation JSON returns robot_feedback, action_schema and observation_contract directly; '
    'read these without opening verbose GUI panels. Request depth_points only for relevant image pixels. '
    'When public sensor records expose simulator depth, it is an authorized sensor input; '
    'use its aligned RGB, depth value, pixel coordinates, units, same-frame camera intrinsics and extrinsics. '
    'No dense depth map is sent by default. These read-only sensor tools do not move the robot; '
    'all physical actions still use GUI controls. Demo tools return original video frames, not an inferred replacement task. '
    'Calculate coordinates yourself from these public records or invoke the available pure arithmetic helper. '
    'Depth is optical-axis Z in metres, not distance along the viewing ray. Check whether the transform uses optical or OpenGL camera axes. '
    'Use the full K matrix and the explicitly named transform direction. '
    'Task coordinates are not world coordinates unless a public task-to-world transform is supplied. '
    'Do not combine different frames or cameras, infer missing calibration, or replace invalid depth with zero. '
    'Depth samples describe visible surfaces, not object centers, grasp poses or guaranteed collision-free targets. '
    'Only simulator depth is supplied. If a depth sample is unavailable, it remains unavailable; '
    'there is no monocular or multiview estimated-depth fallback. '
    'Hidden object poses, semantic masks, evaluator state and task scores are not public sensor inputs.')
FEEDBACK_LOOP_INSTRUCTIONS = (
    'Use a short observation-prediction-action-check loop within this episode. '
    'Before moving, choose the next small objective and an observable expected change. '
    'After Commit, compare requested motion with actual motion, tracking status, gripper feedback and the new image. '
    'Command completion does not establish object movement or grasp success. '
    'If feedback contradicts your expectation, revise the state estimate or approach before repeating the motion. '
    'A tracking failure alone does not identify collision, joint limits or IK as the cause; use only the reported evidence. '
    'Use shorter movements near contact, during uncertain grasps and after unexpected motion. '
    'For visual guidance, use whichever available view shows the target and gripper clearly; '
    'do not assume image up/down always means world forward/back. '
    'When a grasp matters, verify visible object motion with the gripper before treating it as held.')
EPISODE_MEMORY_INSTRUCTIONS = (
    'Keep a compact episode-local working note: current objective, observed state with frame reference, '
    'uncertain hypotheses, last requested versus actual change, failed approach and next check. '
    'Preserve this note through context compaction; update or discard stale facts when new evidence disagrees. '
    'Use only observations and experience from this episode. Do not import task recipes, other episode traces, '
    'development practice, hidden scoring criteria or cross-episode learned skills. '
    'Do not copy every image or the entire action history into the note. '
    'If the program memory tool is available, store this compact note in its JSON memory; '
    'otherwise retain it in your current conversation state. '
    'A final Done summary should name the visible evidence supporting completion; '
    'a Give up reason should identify the observed obstacle and attempted adjustments, without inventing evidence.')
EPISODE_INSTRUCTIONS = '\n\n'.join((TERMINATION_INSTRUCTIONS, WAIT_INSTRUCTIONS,
    GUI_BATCH_INSTRUCTIONS, DEPTH_SENSOR_INSTRUCTIONS,
    FEEDBACK_LOOP_INSTRUCTIONS, EPISODE_MEMORY_INSTRUCTIONS))
STOP_PENDING_INSTRUCTIONS = (
    'An accepted GUI operation is still pending. Await its completion and its new observation. '
    'Do not terminate the pending call or cancel, duplicate, or replay accepted inputs. '
    'Infrastructure waiting is not a reason to end the episode.')
STOP_CONTINUE_INSTRUCTIONS = (
    'This episode has no confirmed terminal state. Continue the original task in this native session. '
    + TERMINATION_INSTRUCTIONS + ' ' + WAIT_INSTRUCTIONS)
