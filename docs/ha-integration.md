# Home Assistant Integration

playAIdes can be driven from Home Assistant in two ways:
1. **HTTP triggers** — HA tells playAIdes to swap, dismiss, or query state.
2. **Skills delegation** — the user invokes HA's conversation agent through a persona by prefixing utterances with a configured "house word."

This doc is the HA-side configuration reference. The architecture is documented in `docs/superpowers/specs/2026-04-26-ha-integration-design.md`.

## Prerequisites

- A Home Assistant instance reachable from the playAIdes host.
- A long-lived access token. Settings → Profile → Long-Lived Access Tokens → Create Token. Copy the value immediately — HA does not store it.
- For skills: at least one configured conversation agent with an LLM backend (Settings → Voice Assistants → New Assistant → pick an LLM-backed agent like the OpenAI integration, Google AI, or HA's local LLM via Ollama).

## playAIdes-side environment

```bash
export PLAYAIDES_API_KEY="some-long-random-string"  # Bearer token HA must send
export HA_URL="http://homeassistant.local:8123"
export HA_TOKEN="<long-lived-token>"
export HA_DEFAULT_AGENT_ID="conversation.openai_assist"  # find in HA logs or Settings
```

`PLAYAIDES_API_KEY` left unset = dev mode (no auth check, with a startup warning). Do NOT leave it unset on a network-exposed host.

## HA-side YAML

### `secrets.yaml`

```yaml
playaides_api_key: "Bearer some-long-random-string"
```

### `configuration.yaml` — `rest_command:` block

```yaml
rest_command:
  playaides_activate_persona:
    url: "http://playaides.local:8765/api/personas/{{ persona_id }}/activate"
    method: POST
    headers:
      Authorization: !secret playaides_api_key
    timeout: 5

  playaides_dismiss:
    url: "http://playaides.local:8765/api/dismiss"
    method: POST
    headers:
      Authorization: !secret playaides_api_key
    timeout: 5
```

### Sample automations

**Show Silver in the kitchen at 7 AM:**
```yaml
alias: Morning Silver
triggers:
  - trigger: time
    at: "07:00:00"
actions:
  - action: rest_command.playaides_activate_persona
    data:
      persona_id: silver
  - action: fully_kiosk.load_url
    data:
      url: "http://playaides.local:8765/?persona=silver"
    target:
      device_id: <kitchen-tablet-device-id>
```

**Bedtime — dismiss across all TVs:**
```yaml
alias: Bedtime Persona Dismiss
triggers:
  - trigger: state
    entity_id: input_boolean.bedtime_routine
    to: "on"
actions:
  - action: rest_command.playaides_dismiss
```

### Polling state for a dashboard widget

```yaml
sensor:
  - platform: rest
    name: PlayAIdes Active Persona
    resource: http://playaides.local:8765/api/state
    value_template: "{{ value_json.active_persona_id or 'none' }}"
    json_attributes:
      - bound_client_count
    scan_interval: 30
```

(`/api/state` is unauthenticated by design — read-only, no PII.)

## Per-persona skills config (`personas/<id>/persona.json`)

```jsonc
{
  "name": "Silver",
  "wake_words": ["Hey Silver"],
  "dismiss_words": ["Goodnight Silver"],

  "house_words": ["house"],
  "rephrase_ha_response": false,
  "ha_agent_id": "conversation.openai_assist"
}
```

- `house_words`: keywords (case-insensitive, prefix-only) that route the residual to HA. Empty = HA delegation disabled.
- `rephrase_ha_response`: if true, HA's response is restyled by the persona's own LLM before TTS. Adds latency.
- `ha_agent_id`: which HA conversation agent to address. Omit to use `HA_DEFAULT_AGENT_ID`.

Find your agent_id in Settings → Voice Assistants — the entity_id pattern is `conversation.<name>`.

## Manual smoke test

1. Start playAIdes with the env vars above set.
2. Open the viewer: `http://playaides.local:8765/?persona=silver`.
3. From a host that can reach playAIdes:
   ```bash
   # Activate (no browser reload):
   curl -X POST -H "Authorization: $PLAYAIDES_API_KEY" \
     http://playaides.local:8765/api/personas/silver/activate

   # State:
   curl http://playaides.local:8765/api/state

   # Dismiss:
   curl -X POST -H "Authorization: $PLAYAIDES_API_KEY" \
     http://playaides.local:8765/api/dismiss
   ```
4. With Silver active, say or type "house, what's the temperature in the kitchen". Confirm:
   - Lipsync fires.
   - HA logs (`config/home-assistant.log`) show a conversation hit.
   - The response matches what HA's conversation agent returned (or a rephrased version if you enabled `rephrase_ha_response`).

## Future phases (not yet implemented)

- **Phase 3**: HA → persona event-driven automations (e.g. "door opened → say welcome home"). See spec § 7.1.
- **Phase 4**: HACS `homeassistant-playaides` custom_component so HA voice satellites can use a persona as their conversation agent. See spec § 7.2.
