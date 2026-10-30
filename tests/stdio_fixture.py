"""Offline SDK fixture launched as a real stdio subprocess; never shipped as a CLI option."""

import os
import time
from datetime import datetime

import qai_hub as hub

from qualcomm_ai_hub_mcp.server import create_server


class Inference(hub.InferenceJob):
    def __init__(self, owner):
        hub.Job.__init__(
            self,
            owner,
            "j-fixture",
            "offline",
            datetime.now(),
            "test",
            "",
            "p-fixture",
            False,
            hub.JobType.INFERENCE,
            [hub.JobStatus.State.CREATED],
        )
        self.profiling = True

    def wait(self, timeout=None):
        time.sleep(0.4)
        if timeout == 1:
            raise TimeoutError("secret-test-token")
        return hub.JobStatus(hub.JobStatus.State.SUCCESS)

    def get_status(self):
        return hub.JobStatus(hub.JobStatus.State.RUNNING_INFERENCE)


class SDK:
    config = hub.ClientConfig("offline-test-token")

    def __init__(self):
        self.job = Inference(self)

    def get_devices(self, name="", os="", attributes=None):
        print("SDK progress: stdout must never contaminate protocol", flush=True)
        import os as operating_system

        operating_system.write(1, b"SDK native stdout noise\n")
        if name == "error":
            raise ValueError("secret-test-token")
        return [
            hub.Device(
                name="Offline Test Device", os="test", attributes=["offline:true"]
            )
        ]

    def _web_url_of_job(self, job_id):
        return "https://example.invalid/jobs/" + job_id

    def _web_url_of_model(self, model_id):
        return "https://example.invalid/models/" + model_id

    def get_job(self, job_id, job_type=None):
        return self.job

    def get_model(self, model_id):
        return hub.Model(
            self,
            model_id,
            datetime.now(),
            hub.SourceModelType.ONNX,
            "model",
            {},
            None,
            False,
            None,
            {},
            {},
        )

    def submit_inference_job(self, **kwargs):
        return self.job


if __name__ == "__main__":
    create_server(workspace=os.environ.get("QAI_MCP_TEST_WORKSPACE"), sdk=SDK()).run(
        transport="stdio"
    )
