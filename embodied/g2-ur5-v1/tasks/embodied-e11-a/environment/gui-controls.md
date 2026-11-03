# VideoICL robot GUI

Observe the complete GUI screenshot before acting. It shows the assigned task,
head/left-wrist/right-wrist RGB cameras, robot TCP poses, read-only joint angles,
gripper opening, the previous movement's measured tracking error, and budgets.
Robot positions use metres, orientations use quaternion wxyz, and joints use
radians. The room-local task axes are +X forward, +Y left, and +Z up. A camera's
image axes can differ from the task axes.

Choose one button for each arm, enter the translation distance in **mm** and
rotation angle in **degrees**, then click **Commit**. Both arms execute that
submission together. Selecting buttons or editing fields does not advance the
robot. Each Commit consumes one paired physical action. Read the updated image
and measured feedback before the next Commit. The GUI shows the allowed numeric
ranges for this robot; a requested movement can be limited by its actual reach.

| Button | Effect on the selected arm |
| --- | --- |
| STILL | Hold the current target pose and gripper state. |
| FWD / BACK | Translate along task +X / -X by the entered distance. |
| LEFT / RIGHT | Translate along task +Y / -Y by the entered distance. |
| UP / DOWN | Translate along task +Z / -Z by the entered distance. |
| ROTATE_CCW / ROTATE_CW | Rotate about task +Z by the positive / negative entered angle. |
| PITCH_UP / PITCH_DOWN | Rotate about task +Y by the positive / negative entered angle. |
| ROLL_LEFT / ROLL_RIGHT | Rotate about task +X by the positive / negative entered angle. |
| GRASP | Close the gripper while holding its target pose. |
| RELEASE | Open the gripper while holding its target pose. |

Use separate submissions for movement and gripper changes on the same arm.
Rotations follow the right-hand rule. **Refresh** reads the current observation
without submitting a physical action. Video controls play, pause, or seek the
assigned RGB demonstration; demo frame tools may also inspect its timestamps.
The text condition provides the assigned explicit rule instead of a video.
Demonstrations contain no expert robot poses or joint/action trajectories.

The model tools are **observe**, **act**, **done**, and **giveup**, plus read-only
demo frame tools when a video is assigned. `act` sends mouse, keyboard, text,
scroll, or short wait inputs to this GUI, referencing its latest screenshot.
Submit at most one physical Commit per `act` call. Use the visible controls;
there is no depth query, pixel backprojection, camera calibration, object pose,
hidden world-state query, direct robot API, or task-score feedback.

**Done** declares that you believe the task is complete. **Give up** ends an
attempt you cannot complete. An optional explanation can be typed in the stop
reason box. The corresponding model tools activate these same GUI buttons.
Both stop further actions and preserve the final physical state for independent
native checking. A completion claim does not determine native success. Interim
success is private and does not stop the attempt. Budget exhaustion also ends
the attempt. No correctness report about an inferred demonstration rule is
required before acting.
