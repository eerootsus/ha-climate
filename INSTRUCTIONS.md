# Pyscript Chore Management Setup

## What's Configured

### People
| Name | Person Entity | Notification Service |
|------|---------------|---------------------|
| Eero | person.eero_otsus | notify.mobile_app_fp5 |
| Kätlyn | person.katlyn_koritski | notify.mobile_app_katu_iphone |
| Lola | person.lola_laur | (none) |

### Rotating Chores (Weekly)
| Chore | Entity | Rotation |
|-------|--------|----------|
| Pesutoimkond | input_select.chore_laundry | Eero -> Kätlyn -> Lola |
| Prügitoimkond | input_select.chore_trash | Eero -> Kätlyn -> Lola |
| Tualetitoimkond | input_select.chore_bathroom | Eero -> Kätlyn -> Lola |
| Floratoimkond | input_select.chore_plants | Eero -> Kätlyn -> Lola |
| Kassitoimkond | input_select.chore_cat | Eero -> Kätlyn -> Lola |
| Õuetoimkond | input_select.chore_outdoor | Eero -> Kätlyn |
| Tolmutoimkond | input_select.chore_dust | Eero -> Kätlyn -> Lola |

### Dinner Schedule (Fixed by Weekday)
| Day | Cook |
|-----|------|
| Monday | Kätlyn |
| Tuesday | Lola |
| Wednesday | Eero |
| Thursday | Lola |
| Friday | Kätlyn |
| Saturday | Eero |
| Sunday | Kätlyn |

---

## Home Assistant Setup

### Prerequisites
- Pyscript integration installed (via HACS or manual)

### Step 1: Copy Files to HA Config

```
config/
├── pyscript/
│   └── chores.py         <- copy this
├── chores/
│   └── package.yaml      <- copy this folder
└── configuration.yaml
```

### Step 2: Include Package in configuration.yaml

```yaml
homeassistant:
  packages:
    chores: !include chores/package.yaml
```

### Step 3: Restart Home Assistant

Settings -> System -> Restart

---

## How It Works

### Chore Rotation
- Every Monday at 00:01, pyscript rotates all chores to the next person
- Each chore's rotation is independent (different people may be assigned)
- State is stored in `input_select` entities (survives restarts)

### Notifications
- **Daily dinner reminder** at 10:00 - notifies today's cook
- **Weekly chore summary** at 08:00 Monday - each person gets their weekly chores

### Sensors
- `sensor.chore_*` - Shows friendly name of current assignee
- `sensor.dinner_today` / `sensor.dinner_tomorrow` - Shows today's/tomorrow's cook

---

## Manual Services

Call from Developer Tools -> Services:

- `pyscript.chores_rotate_now` - Manually trigger rotation
- `pyscript.chores_send_summaries` - Manually send weekly summaries

---

## Modifying Configuration

Edit `pyscript/chores.py` to change:
- People and notification services (`PEOPLE` dict)
- Chores and rotations (`ROTATING_CHORES` list)
- Dinner schedule (`DINNER_SCHEDULE` dict)

After editing, reload pyscript:
- Developer Tools -> YAML -> Reload Pyscript
