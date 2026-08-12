# Mobile Use Universal contract fixtures

- Source repository commit: `e5f81dc5e86594a78759943ad88ca69d52367684`
- Source files: `src/mobile_use.py`, `src/case_runner.py`
- Source symbols: `MobileUseClient._do_call_universal`,
  `run_agent_task_one_step`, `list_agent_run_current_step_raw`,
  `get_agent_result_raw`, `cancel_task_raw`,
  `_extract_current_step_signal`, `_is_done_by_get_result`,
  `_infer_case_status_reason_from_result_payload`
- Sanitized fields: account IDs, PodId, ProductId, RunId, RequestId,
  screenshot URLs and user content.
- Structural fields, action names, casing, wrappers and enum values are unchanged.
- Fixtures are copied into this repository and never read from the source
  checkout at test runtime.

## Official API references

- `RunAgentTask`: <https://www.volcengine.com/docs/6394/1953046>
- `ListAgentRunCurrentStep`: <https://www.volcengine.com/docs/6394/1953039>
- `GetAgentResult`: <https://www.volcengine.com/docs/6394/1953054>
- `CancelTask`: <https://www.volcengine.com/docs/6394/1953044>

## SHA-256

- `cancel_accepted.json`: `10850bdfe386551e078e20b7beb3c64bffe71029c42fdd9566ec8af712e30314`
- `result_cancelled.json`: `dd8d39e8777dfdfd842afafae10ce2ad79fa98ab7fc094cb1a36b46513f02b44`
- `result_fail_content.json`: `ef6ee806cf20d0c712a265e21b9cf8885e800ef97050f66f585eaa9c2a9fefc9`
- `result_pass_struct.json`: `edd96e6a4f67492ec3f7aa164cfe5efbb89ae835ab2613b4846b8917b72da8b2`
- `result_pending.json`: `13a33d65e70689e2ee533cba57c73b5277d4064cdd65e885711e3e056ffb1ca5`
- `run_started.json`: `f75ab968d51033bb8e9f7e000b2b8402f4874aa82e0f741d163492d93560fa32`
- `step_finished.json`: `38547a67f14c21fea157b8981893dba29b50e0f840f0b0fc22c49974f69a71a2`
- `step_request_user.json`: `5131e4109805ef2b4dd1d070b23cdf018b67bb3f8b1a4a22cc0d5828783dff14`
