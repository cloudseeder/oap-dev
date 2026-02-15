# OAP for Robotics: Manifests as the Cognitive Interface for Physical Capabilities

OAP was designed for software capabilities — APIs, command-line tools, services. But the manifest format is protocol-agnostic and the design philosophy is universal. Every principle that makes OAP work for software applies directly to physical capabilities: sensors, actuators, tools, and robotic systems.

A gripper is an agent with a manifest.

## The problem OAP solves in robotics

Today, a robot that encounters a new tool requires pre-programmed knowledge or retraining. The integrator writes custom drivers, maps every input and output, and hardcodes the interaction. Swap the gripper for a different model and the code changes. Add a new sensor and someone has to write the glue.

This is the same problem OAP solves in software: capabilities exist, but the AI doesn't know about them at runtime. The solution is the same too. Publish a manifest that describes what the capability does, what it accepts, what it produces, and how to invoke it. Let the AI read the description and decide if it fits the task.

A robot with access to OAP discovery doesn't need to be pre-programmed for every tool it might use. It reads manifests, reasons about capabilities, and invokes them — the same way an LLM reads a manifest for a text summarizer and decides to call it.

## How it maps

| Software concept | Robotics equivalent |
|-----------------|---------------------|
| API endpoint | Actuator, sensor, tool, subsystem |
| `description` | What the hardware does — the AI planner reads this |
| `input` | Command format: target position, force, speed, parameters |
| `output` | Response: sensor readings, status, measurements |
| `invoke` | Protocol to reach it: HTTP, ROS 2 service, MQTT, serial, DDS |
| `health` | Is the hardware operational, calibrated, powered? |
| `examples` | Sample commands with expected responses |
| `tags` | Capability categories: manipulation, sensing, mobility, vision |
| Web crawling for discovery | mDNS, NFC tags, QR codes, network scan, USB enumeration |
| Trust overlay | Safety certification, calibration status, maintenance records |

The manifest format doesn't change. A physical capability is described the same way as a software one.

## Manifest examples

### A robotic gripper

```json
{
  "oap": "1.0",
  "name": "UR5e Parallel Gripper",
  "description": "Parallel jaw gripper mounted on a UR5e collaborative robot arm, cell 3. Grasps objects 10-85mm wide with adjustable force from 20-235N. Cycle time approximately 300ms open-to-close. Suitable for pick-and-place of rigid parts, electronics, and packaged goods. Not suitable for deformable objects or items under 10mm. Returns measured grip width and applied force after each command.",
  "input": {
    "format": "application/json",
    "description": "JSON object with 'action' ('grip' or 'release'), 'width_mm' (target width, 10-85), 'force_n' (grip force, 20-235), and optional 'speed_pct' (0-100, default 50)."
  },
  "output": {
    "format": "application/json",
    "description": "JSON with 'status' (gripped|released|error|object_detected|no_object), 'measured_width_mm', 'applied_force_n', 'timestamp_ms'."
  },
  "invoke": {
    "method": "POST",
    "url": "http://ur5e-cell-3.local:8080/gripper"
  },
  "examples": [
    {
      "input": {"action": "grip", "width_mm": 50, "force_n": 100, "speed_pct": 75},
      "output": {"status": "gripped", "measured_width_mm": 48.2, "applied_force_n": 100, "timestamp_ms": 1708012345678},
      "description": "Grip a 50mm object at 100N"
    },
    {
      "input": {"action": "release"},
      "output": {"status": "released", "measured_width_mm": 85.0, "applied_force_n": 0, "timestamp_ms": 1708012345980},
      "description": "Release (fully open)"
    }
  ],
  "health": "http://ur5e-cell-3.local:8080/health",
  "tags": ["robotics", "gripper", "manipulation", "ur5e", "collaborative"],
  "version": "2.1.0"
}
```

### A LIDAR sensor

```json
{
  "oap": "1.0",
  "name": "Velodyne VLP-16 LIDAR",
  "description": "16-channel 3D LIDAR scanner producing 300,000 points per second. 360-degree horizontal field of view, 30-degree vertical (-15 to +15). Range 1-100 meters. Returns point clouds as binary PCD or JSON arrays. Supports single-scan snapshots and continuous streaming. Mounted at 1.5m height on mobile platform alpha-2.",
  "input": {
    "format": "application/json",
    "description": "JSON with 'mode' ('snapshot' or 'stream'), optional 'duration_sec' for stream mode (default 1.0), optional 'format' ('pcd' or 'json', default 'pcd'), optional 'max_range_m' to filter distant points."
  },
  "output": {
    "format": "application/octet-stream",
    "description": "PCD point cloud file (binary) or JSON array of {x, y, z, intensity, ring} objects. Each point in sensor frame coordinates (meters). Streaming mode sends chunked responses."
  },
  "invoke": {
    "method": "POST",
    "url": "http://alpha-2.local:9100/lidar/scan",
    "streaming": true
  },
  "health": "http://alpha-2.local:9100/health",
  "tags": ["robotics", "lidar", "perception", "3d", "point-cloud", "velodyne"]
}
```

### A mobile base

```json
{
  "oap": "1.0",
  "name": "Clearpath Husky A200",
  "description": "Four-wheel differential drive mobile platform. Maximum speed 1.0 m/s. Payload capacity 75kg. Operates indoors and outdoors on flat to moderate terrain. Accepts velocity commands (linear and angular) or waypoint navigation goals. Returns odometry and navigation status. Emergency stop available via health endpoint. Platform name: warehouse-bot-1.",
  "input": {
    "format": "application/json",
    "description": "JSON with 'command' type. 'velocity': {linear_ms: float, angular_rads: float, duration_sec: float}. 'navigate': {goal_x: float, goal_y: float, goal_theta: float} in map frame. 'stop': {} for immediate stop."
  },
  "output": {
    "format": "application/json",
    "description": "JSON with 'status' (moving|arrived|stopped|blocked|error), 'pose' {x, y, theta}, 'velocity' {linear_ms, angular_rads}, 'battery_pct'."
  },
  "invoke": {
    "method": "POST",
    "url": "http://warehouse-bot-1.local:8090/base/command"
  },
  "health": "http://warehouse-bot-1.local:8090/health",
  "tags": ["robotics", "mobile-base", "navigation", "differential-drive"]
}
```

### A tool changer

```json
{
  "oap": "1.0",
  "name": "ATI QC-21 Tool Changer",
  "description": "Automatic tool changer on robot arm cell-7. Locks and unlocks end-of-arm tools. Compatible with tools up to 21kg. Lock/unlock cycle time under 1 second. Reports current tool ID via integrated RFID reader. Must be in safe position before changing tools — verify arm is at tool-change waypoint before issuing commands.",
  "input": {
    "format": "application/json",
    "description": "JSON with 'action' ('lock', 'unlock', or 'identify'). 'lock' and 'unlock' require arm to be at tool-change position."
  },
  "output": {
    "format": "application/json",
    "description": "JSON with 'status' (locked|unlocked|error), 'tool_id' (RFID tag value or null if no tool), 'tool_name' (from tool registry if known)."
  },
  "invoke": {
    "method": "POST",
    "url": "http://cell-7.local:8080/tool-changer"
  },
  "health": "http://cell-7.local:8080/tool-changer/health",
  "tags": ["robotics", "tool-changer", "end-effector", "ati"]
}
```

## Discovery in physical space

Software discovery crawls the web. Robotics discovery scans the physical environment. Different mechanisms, same pattern: find manifests, embed descriptions, match intents.

### Local network discovery

The most natural fit. Every capability on the robot's network publishes a manifest at a known path. A local crawler scans the network and indexes what it finds.

- **mDNS/DNS-SD**: Capabilities register as `_oap._tcp.local` services. The discovery agent resolves them and fetches manifests from the announced endpoint. Zero configuration.
- **Known hosts**: A config file lists expected devices on the network (like seeds in the web crawler). The crawler fetches manifests on startup and watches for changes.
- **HTTP at `/.well-known/oap.json`**: Same convention as the web. Every device with an HTTP interface publishes its manifest at the well-known path.

### Physical tagging

For tools and peripherals that aren't always connected:

- **NFC tags**: Tap the tool to the robot's reader. The tag contains the manifest URL or the manifest itself (it's small enough). The robot discovers the capability on contact.
- **QR codes**: Print the manifest URL on the tool. A camera reads it, the robot fetches the manifest. Works for tools in a shared crib.
- **USB descriptor**: When a USB device is plugged in, the robot checks for an OAP manifest in the device descriptor or at a known endpoint.

### Hierarchical discovery

A robot cell might have dozens of capabilities. Rather than discovering each one individually, the cell controller publishes a manifest index — a list of all capabilities in the cell. The robot fetches the index and gets everything at once.

```json
{
  "oap": "1.0",
  "name": "Cell 3 — Assembly Station",
  "description": "Robotic assembly cell with a UR5e arm, parallel gripper, vacuum gripper, torque driver, and two Intel RealSense cameras. Capable of pick-and-place, screw driving, visual inspection, and part verification. Query individual capability manifests for specific invocation details.",
  "invoke": {
    "method": "GET",
    "url": "http://cell-3.local:8080/oap/capabilities"
  },
  "tags": ["robotics", "cell", "assembly", "index"]
}
```

The invoke URL returns an array of manifests — one per capability in the cell. Discovery indexes them all.

## Trust is safety

In software, the trust overlay verifies domain ownership and capability claims. In robotics, trust is a safety question. An uncertified actuator, an uncalibrated sensor, or an expired maintenance record can cause physical harm.

The trust layers map directly:

### Layer 0 — Baseline (is it reachable and responsive?)

- Health endpoint returns 200
- Manifest is valid and parseable
- Network latency is within acceptable bounds for real-time control

This is the minimum. A robot should never invoke a capability whose health check fails.

### Layer 1 — Identity (is this really what it claims to be?)

- Device certificate matches the manifest's claimed identity
- Serial number in the manifest matches the physical device
- The device is on the expected network segment (not a rogue device)

Prevents a compromised device from impersonating a safety-rated tool. The DNS challenge from the web trust spec becomes a device certificate challenge.

### Layer 2 — Capability (can it actually do what it says?)

- Calibration is current (last calibrated within required interval)
- Safety certification is valid (ISO 10218, ISO/TS 15066 for collaborative robots)
- Maintenance schedule is current
- Force limits, speed limits, and workspace boundaries are correctly configured
- Self-test passes (the capability can demonstrate its claimed function)

This is where robotics trust goes beyond software trust. A gripper that claims 235N max force needs to prove its force sensor is calibrated. A mobile base that claims 1.0 m/s max speed needs a valid safety configuration.

### Layer 3 — Compliance (is it certified for this environment?)

- CE marking, NRTL listing, or equivalent for the deployment region
- Risk assessment for the specific application (ISO 12100)
- Environmental rating (IP rating, temperature range, clean room class)
- Integration testing records for the specific robot cell

A robot planner that understands trust layers can make safety-aware decisions: "The gripper is reachable (Layer 0) and identified (Layer 1), but its calibration expired yesterday (Layer 2 failed). I'll skip this tool and use the other gripper on cell 4."

## The AI planner as discovery client

The real power of OAP in robotics isn't just describing capabilities — it's enabling AI planners to reason about them dynamically.

Consider a task: "Pick up the red gear from bin A and place it in the fixture."

Without OAP, the planner has hardcoded knowledge of every tool: which gripper, which camera, which arm, which coordinate frames. Change any component and the planner breaks.

With OAP:

1. **Planner queries discovery**: "I need to detect a red gear in a bin" → finds the RealSense camera manifest
2. **Planner queries discovery**: "I need to pick up a 35mm metal part" → finds the parallel gripper manifest (not the vacuum gripper — the description says "rigid parts")
3. **Planner reads manifests**: Understands the input/output format for each capability
4. **Planner checks trust**: Both capabilities are healthy, identified, and calibrated
5. **Planner invokes**: Camera → detect gear pose → gripper → pick at detected pose → arm → move to fixture → gripper → release

If the parallel gripper goes down, the planner re-queries discovery: "I need to pick up a 35mm metal part" — and this time the vacuum gripper comes back (if its description covers rigid parts). The plan adapts without code changes.

This is the same pattern as an LLM discovering a text summarizer at runtime instead of having it hardcoded. The difference is that the stakes are higher (physical safety) and the latency requirements are tighter (real-time control). Both are addressed: safety through the trust overlay, latency through local discovery (no internet round-trips).

## What the spec already handles

OAP's existing manifest format covers robotics without modification:

- **`description`**: The AI planner reads this to decide if a capability fits a task. "Grasps objects 10-85mm wide" is exactly the information a planner needs.
- **`input` / `output`**: Command and response formats. JSON over HTTP works for most robotic interfaces that aren't hard real-time.
- **`invoke`**: HTTP endpoints work for supervisory control. The spec already supports `stdio` for local commands. A `ros2` or `mqtt` method would be a natural extension but isn't required — many modern robotic systems expose HTTP APIs.
- **`health`**: Critical for robotics. A health check that returns 200 means the hardware is powered, connected, and responsive.
- **`examples`**: Sample commands with expected outputs. Essential for an AI planner to learn the interaction pattern.
- **`tags`**: Free-form hints for indexing. The planner can filter by `robotics`, `gripper`, `manipulation`, etc.
- **`version`**: Firmware or capability version. Important for compatibility checking.

## What might need to evolve

Some robotics concepts don't have a direct home in the current spec, but fit naturally as extensions:

**Real-time constraints.** Some robotic control requires millisecond-level latency (servo control, force feedback). OAP's HTTP invoke model works for supervisory control (task-level commands) but not for tight servo loops. A future extension might add latency or protocol hints to the invoke spec.

**Coordinate frames.** Robotic capabilities operate in spatial frames (base frame, tool frame, world frame). The manifest could include a reference frame identifier so the planner knows how to transform coordinates. Today, this information goes in the `description` or `docs`.

**Safety constraints.** Maximum force, speed limits, workspace boundaries. These are critical for planning and could be structured fields rather than free text in the description. The trust overlay is the natural home for this — Layer 2 capability attestation could include machine-readable safety parameters.

**State dependencies.** "Must be at tool-change position before unlocking" is a precondition. Planning systems need these, but encoding them in a manifest risks over-specifying the format. The description handles this for now.

## The vision

OAP started with a simple observation: AI needs a way to learn about capabilities at runtime. In software, those capabilities are APIs and tools. In robotics, they're sensors, actuators, and subsystems.

The manifest is the universal interface. A description that an AI can read, inputs and outputs it can reason about, an invocation method it can call. Whether the capability is a text summarizer on the internet or a gripper on a factory floor, the cognitive interface is the same.

Standardize the format. Let the ecosystem build the discovery. Let the AI reason about what's available and what fits the task. One file. One location. One manifest.

Publish and the robot knows what you can do.
