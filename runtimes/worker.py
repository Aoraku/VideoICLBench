"""Authenticated host lifecycle service. Run only on a dedicated execution host.

This manages real VMs/AVDs. Task-specific guest initialization and certification
remain separate from VM provisioning; the control plane fails closed until wired.
"""

import base64
import hmac
import io
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import uuid
import xml.etree.ElementTree as ET
from fastapi import FastAPI, Depends, Header, HTTPException
from pydantic import BaseModel, ConfigDict
from PIL import Image

DATA = Path(os.environ.get("VIC_WORKER_DATA", "/srv/videoicl/instances"))
PROFILES = Path(os.environ.get("VIC_WORKER_PROFILES", "/etc/videoicl/profiles.json"))


def shell(args, timeout=120):
    r = subprocess.run(args, capture_output=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError(r.stderr.decode(errors="replace")[-2000:])
    return r.stdout


def domain_xml(template, name, image):
    root = ET.fromstring(template)
    disks = root.findall('./devices/disk[@device="disk"]')
    if len(disks) != 1:
        raise ValueError("Template must contain exactly one writable OS disk")
    disk = disks[0]
    disk.set("type", "file")
    source = disk.find("source")
    if source is None:
        source = ET.SubElement(disk, "source")
    source.attrib.clear()
    source.set("file", str(image))
    root.find("name").text = name
    prior_uuid = root.find("uuid")
    if prior_uuid is not None:
        root.remove(prior_uuid)
    # Firmware variables must also be isolated; this worker requires stateless firmware.
    if root.find("./os/nvram") is not None:
        raise ValueError(
            "NVRAM isolation must be configured before using a UEFI template"
        )
    for mac in root.findall("./devices/interface/mac"):
        mac.set(
            "address",
            "52:54:00:" + ":".join(f"{b:02x}" for b in uuid.uuid4().bytes[:3]),
        )
    for graphic in root.findall("./devices/graphics"):
        graphic.set("listen", "127.0.0.1")
        graphic.set("autoport", "yes")
        graphic.set("port", "-1")
        for listen in graphic.findall("listen"):
            listen.set("address", "127.0.0.1")
    return ET.tostring(root, encoding="unicode")


def create_app():
    secret = os.environ.get("VIC_WORKER_TOKEN", "")
    if len(secret) < 32:
        raise RuntimeError("VIC_WORKER_TOKEN must have at least 32 characters")
    DATA.mkdir(parents=True, exist_ok=True)
    profiles = json.loads(PROFILES.read_text())
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    lifecycle_lock = threading.RLock()

    def auth(authorization: str = Header(default="")):
        if not hmac.compare_digest(authorization, "Bearer " + secret):
            raise HTTPException(403, "Worker credential required")

    class Create(BaseModel):
        model_config = ConfigDict(extra="forbid")
        profile: str

    def folder(instance_id):
        if not re.fullmatch("[a-f0-9]{32}", instance_id):
            raise HTTPException(404, "Unknown instance")
        dest = DATA / instance_id
        if not (dest / "instance.json").exists():
            raise HTTPException(404, "Unknown instance")
        return dest

    def provision(instance_id, profile):
        spec = profiles[profile]
        dest = DATA / instance_id
        dest.mkdir(exist_ok=True)
        name = "vic-" + instance_id
        if spec["driver"] == "libvirt":
            image = Path(spec["base_image"]).resolve(strict=True)
            target = dest / "disk.qcow2"
            shell(
                [
                    "qemu-img",
                    "create",
                    "-f",
                    "qcow2",
                    "-F",
                    "qcow2",
                    "-b",
                    str(image),
                    str(target),
                ]
            )
            xml = domain_xml(Path(spec["domain_template"]).read_text(), name, target)
            (dest / "domain.xml").write_text(xml)
            shell(["virsh", "-c", "qemu:///system", "create", str(dest / "domain.xml")])
            info = dict(
                id=instance_id,
                profile=profile,
                driver="libvirt",
                name=name,
                status="running",
            )
        elif spec["driver"] == "android":
            # Single configured AVD is exclusive until per-instance AVD cloning is configured.
            for manifest in DATA.glob("*/instance.json"):
                existing = json.loads(manifest.read_text())
                if (
                    existing.get("driver") == "android"
                    and existing.get("status") == "running"
                ):
                    raise ValueError(
                        "Android port is in use; per-instance AVD and port allocation are required for concurrency"
                    )
            log = (dest / "emulator.log").open("ab")
            proc = subprocess.Popen(
                [
                    "emulator",
                    "-avd",
                    spec["avd"],
                    "-snapshot",
                    spec["snapshot"],
                    "-no-snapshot-save",
                    "-no-window",
                    "-port",
                    "5554",
                ],
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
            log.close()
            info = dict(
                id=instance_id,
                profile=profile,
                driver="android",
                pid=proc.pid,
                serial="emulator-5554",
                status="running",
            )
        else:
            raise ValueError("Unsupported driver")
        (dest / "instance.json").write_text(json.dumps(info, indent=2))
        return info

    def destroy(dest):
        info = json.loads((dest / "instance.json").read_text())
        if info["status"] == "destroyed":
            return info
        if info["driver"] == "libvirt":
            shell(["virsh", "-c", "qemu:///system", "destroy", info["name"]])
        else:
            shell(["adb", "-s", info["serial"], "emu", "kill"])
        info["status"] = "destroyed"
        (dest / "instance.json").write_text(json.dumps(info))
        return info

    @app.get("/healthz", dependencies=[Depends(auth)])
    def health():
        return dict(
            profiles=list(profiles),
            kvm=Path("/dev/kvm").exists(),
            task_adapters_connected=False,
        )

    @app.post("/instances", dependencies=[Depends(auth)])
    def create(body: Create):
        if body.profile not in profiles:
            raise HTTPException(422, "Profile is not allowlisted")
        try:
            with lifecycle_lock:
                return provision(uuid.uuid4().hex, body.profile)
        except (ValueError, RuntimeError, FileNotFoundError) as e:
            raise HTTPException(503, str(e))

    @app.post("/instances/{instance_id}/reset", dependencies=[Depends(auth)])
    def reset(instance_id):
        with lifecycle_lock:
            dest = folder(instance_id)
            info = destroy(dest)
            if (dest / "disk.qcow2").exists():
                (dest / "disk.qcow2").unlink()
            return provision(instance_id, info["profile"])

    @app.delete("/instances/{instance_id}", dependencies=[Depends(auth)])
    def delete(instance_id):
        with lifecycle_lock:
            dest = folder(instance_id)
            result = destroy(dest)
            if (dest / "disk.qcow2").exists():
                (dest / "disk.qcow2").unlink()
            return result

    @app.get("/instances/{instance_id}/observation", dependencies=[Depends(auth)])
    def screenshot(instance_id):
        dest = folder(instance_id)
        info = json.loads((dest / "instance.json").read_text())
        if info["status"] != "running":
            raise HTTPException(409, "Instance is not running")
        if info["driver"] == "android":
            raw = shell(["adb", "-s", info["serial"], "exec-out", "screencap", "-p"])
        else:
            path = dest / "screen.ppm"
            shell(
                ["virsh", "-c", "qemu:///system", "screenshot", info["name"], str(path)]
            )
            raw = path.read_bytes()
        img = Image.open(io.BytesIO(raw))
        out = io.BytesIO()
        img.save(out, format="PNG")
        return dict(
            image="data:image/png;base64," + base64.b64encode(out.getvalue()).decode(),
            width=img.width,
            height=img.height,
        )

    return app
