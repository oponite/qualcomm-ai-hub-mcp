# Core API coverage

Target: `qai-hub==0.57.0`. The registry exposes 57 tools.

All 22 non-credential client operations and managed-object methods are mapped below.
The SDK source/signatures are pinned and checked by tests. Constructors and configuration
are startup concerns; data classes and enums are represented in schemas/results.

| MCP tool | Official SDK operation | Confirmation |
|---|---|---|
| `get_devices` | `Client.get_devices` | No |
| `get_device_attributes` | `Client.get_device_attributes` | No |
| `get_frameworks` | `Client.get_frameworks` | No |
| `upload_model` | `Client.upload_model` | Required |
| `get_model` | `Client.get_model` | No |
| `get_models` | `Client.get_models` | No |
| `submit_compile_job` | `Client.submit_compile_job` | Required |
| `submit_quantize_job` | `Client.submit_quantize_job` | Required |
| `submit_profile_job` | `Client.submit_profile_job` | Required |
| `submit_inference_job` | `Client.submit_inference_job` | Required |
| `submit_link_job` | `Client.submit_link_job` | Required |
| `submit_compile_and_profile_jobs` | `Client.submit_compile_and_profile_jobs` | Required |
| `submit_compile_and_link_jobs` | `Client.submit_compile_and_link_jobs` | Required |
| `get_job` | `Client.get_job` | No |
| `get_job_summaries` | `Client.get_job_summaries` | No |
| `set_verbose` | `Client.set_verbose` | No |
| `upload_dataset` | `Client.upload_dataset` | Required |
| `get_dataset` | `Client.get_dataset` | No |
| `get_datasets` | `Client.get_datasets` | No |
| `get_project` | `Client.get_project` | No |
| `create_project` | `Client.create_project` | Required |
| `get_projects` | `Client.get_projects` | No |
| `model_download` | `Model.download` | No |
| `model_get_sharing` | `Model.get_sharing` | No |
| `model_modify_sharing` | `Model.modify_sharing` | Required |
| `model_disable_sharing` | `Model.disable_sharing` | Required |
| `model_wait` | `Model.wait` | No |
| `model_get_producer` | `Model.get_producer` | No |
| `dataset_download` | `Dataset.download` | No |
| `dataset_get_expiration_status` | `Dataset.get_expiration_status` | No |
| `dataset_is_expired` | `Dataset.is_expired` | No |
| `dataset_get_sharing` | `Dataset.get_sharing` | No |
| `dataset_modify_sharing` | `Dataset.modify_sharing` | Required |
| `dataset_disable_sharing` | `Dataset.disable_sharing` | Required |
| `job_get_available_artifacts` | `Job.get_available_artifacts` | No |
| `job_wait` | `Job.wait` | No |
| `job_get_status` | `Job.get_status` | No |
| `job_set_name` | `Job.set_name` | Required |
| `job_download_results` | `Job.download_results` | No |
| `job_get_sharing` | `Job.get_sharing` | No |
| `job_modify_sharing` | `Job.modify_sharing` | Required |
| `job_disable_sharing` | `Job.disable_sharing` | Required |
| `job_download_artifacts_for_type` | `Job.download_artifacts_for_type` | No |
| `job_download_job_logs` | `Job.download_job_logs` | No |
| `compilejob_get_target_model` | `CompileJob.get_target_model` | No |
| `compilejob_get_target_shapes` | `CompileJob.get_target_shapes` | No |
| `compilejob_download_target_model` | `CompileJob.download_target_model` | No |
| `quantizejob_get_target_model` | `QuantizeJob.get_target_model` | No |
| `quantizejob_download_target_model` | `QuantizeJob.download_target_model` | No |
| `linkjob_get_target_model` | `LinkJob.get_target_model` | No |
| `linkjob_download_target_model` | `LinkJob.download_target_model` | No |
| `inferencejob_get_output_dataset` | `InferenceJob.get_output_dataset` | No |
| `inferencejob_download_output_data` | `InferenceJob.download_output_data` | No |
| `inferencejob_download_profile` | `InferenceJob.download_profile` | No |
| `model_get_metadata` | `Model.metadata` (property) | No |
| `model_get_input_spec` | `Model.input_spec` (property) | No |
| `model_get_output_spec` | `Model.output_spec` (property) | No |

## Equivalent representations

- `set_session_token` is deprecated and is replaced by startup `ClientConfig`/SDK authentication; credentials are never tool inputs.
- Deprecated `Model.producer` is covered by `model_get_producer`.
- Deprecated `CompileJob.target_shapes` is covered by `compilejob_get_target_shapes`.
- URLs and other public object fields are included in structured records; lazy model metadata/specs have explicit tools.
- Local enum/status/helper functions (for example, `JobStatus.all_running_states` and `Project.get_project_id`) do not call the service. Enum values and status predicates are exposed through schemas/results; project IDs are accepted directly.
- Python-only model objects use validated saved files or existing uploaded IDs. Dataset arrays use lossless tensor descriptors.
- Sharing operations apply to model, dataset and job objects. The SDK exposes project create/get/list, not project deletion.
- Optional in-memory target-model downloads return a saved artifact path over MCP; archives are not extracted.

Official references: [Core API](https://workbench.aihub.qualcomm.com/docs/hub/api.html),
[Client](https://workbench.aihub.qualcomm.com/docs/hub/generated/qai_hub.Client.html),
[profiling migration](https://workbench.aihub.qualcomm.com/docs/hub/faq.html).
