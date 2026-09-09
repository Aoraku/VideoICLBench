import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location(
    "worker", Path(__file__).parents[1] / "runtimes/worker.py"
)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)


def test_vm_template_has_separate_disk_and_identity():
    source = '<domain><name>base</name><uuid>original</uuid><devices><disk type="file" device="disk"><source file="base.qcow2"/></disk><interface><mac address="52:54:00:00:00:00"/></interface><graphics type="vnc" port="5900" listen="0.0.0.0"><listen type="address" address="0.0.0.0"/></graphics></devices></domain>'
    xml = worker.domain_xml(source, "vic-example", "/data/example/disk.qcow2")
    assert "original" not in xml and "base.qcow2" not in xml
    assert "/data/example/disk.qcow2" in xml and "0.0.0.0" not in xml
    with pytest.raises(ValueError):
        worker.domain_xml(
            source.replace("<devices>", "<os><nvram>shared</nvram></os><devices>"),
            "bad",
            "new",
        )
