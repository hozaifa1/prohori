# Entry ALPHA — submitted concept

## Name and one-line pitch
**FREISA** — a four-legged robot that walks a garden, works out which plants are thirsty by looking at them, and sprays those plants with water.

## Problem, users, and why it matters
Household and smallholder plant care wastes water and loses plants to inconsistent watering. Target users: home gardeners and, in the stated future direction, vineyard operators. The team initially scoped vineyards, then retreated to a controlled household tomato-plant arena because vine leaves sit above the robot's camera height and vineyard terrain defeats the robot's gait.

## What the system does
A MangDang MiniPupper 2 quadruped (12 degrees of freedom, digital servos with position feedback, Raspberry Pi 4, Ubuntu 22.04, roughly $500 open-source platform) carries a Luxonis OAK-D-Lite depth camera on 3D-printed custom brackets and a pelvis-mounted sprinkler with the water reservoir directly above it. The robot walks an arena of tomato plants. A classifier trained in Roboflow runs on the OAK-D's dedicated vision processor, so inference does not compete with the Raspberry Pi that drives locomotion. Each plant is labelled healthy or dried-out. A hand-written finite state machine consumes those inference results as state transitions and decides where the robot walks next. When a plant is classified as needing water, the FSM actuates the sprinkler through the Pi's GPIO. An HTTP server exposes status so an operator can check the system is alive, and the robot can notify its owner over Wi-Fi or Bluetooth that a plant has been watered. Configuration is exposed so the system can be retargeted to other plant types.

## Technical approach
- Vision: a Roboflow-trained classifier deployed to the OAK-D-Lite VPU. A `VisionController` Python class wraps model loading, pipeline launch, and result collection.
- Navigation: a finite state machine. The team explicitly considered and rejected integrating the ROS2 SLAM toolbox because of the integration effort required.
- Locomotion: open-loop servo controller. The team notes a closed-loop controller is what would actually unlock legged obstacle clearance and slip compensation, and that they did not build one.
- Deployment: Docker on the Raspberry Pi. Replicated at three sites — Turin, Chicago, Nantes.
- Cloud: none.

## Architecture documentation
Architecture is modelled in SysML using Eclipse Capella and presented as four layered views: operational entities, interconnections between operational entities, system activities, and logical then physical architecture. The activity decomposition names: target recognition via computer vision, data checking, configuration, target position recognition, external communication, sprinkler actuation decision, sprinkler control, and puppy motion control.

## Reproducibility package
Full hardware bill of materials with part links. Assembly instructions including servo ID mapping, neutral-position calibration procedure, ESP32 OTA firmware update over Wi-Fi, and a 500 Kb UART SCS servo protocol note. Custom 3D-printable parts published. Demo programs for display and haptics. MIT license on code, CC BY-SA 4.0 on documentation, REUSE-compliance certified.

## Evaluation
No quantitative task-success metrics are reported. No baselines. No ablations. No failure taxonomy. No latency, throughput, or cost measurements. Correctness is demonstrated by video of the robot performing the task.

## Presentation and reach
A long illustrated build narrative published on Hackster (7,437 views at time of reading), republished on Electromaker; a four-page team interview in The MagPi magazine issue 139; coverage on Tom's Hardware. The write-up is framed as the sequel to the same team's previous contest entry, with returning members deliberately recusing themselves from writing code and acting as advisors instead.

## Team
Six people. Two of them are prior winners of an earlier edition of the same competition series.
