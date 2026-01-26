# Home Assistant Chore Management

Native Home Assistant automations for household chore rotation and notifications.

## What's Configured

### People
| Name | Person Entity | Notification Service |
|------|---------------|---------------------|
| Eero | person.eero_otsus | notify.mobile_app_eeros_iphone |
| Kätlyn | person.katlyn_otsus | notify.mobile_app_katu_iphone |
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

### Step 1: Copy Files to HA Config

```
config/
├── chores/
│   ├── package.yaml                      <- input_selects and input_datetime
│   ├── sensors/
│   │   ├── chores.yaml                   <- chore sensors
│   │   └── dinner.yaml                   <- dinner sensors
│   └── automations/
│       ├── rotation.yaml                 <- weekly rotation
│       ├── weekly_summary.yaml           <- Monday summary notifications
│       ├── dinner_reminder.yaml          <- daily dinner reminders
│       └── washer_finished.yaml          <- washer notification
└── configuration.yaml
```

### Step 2: Include Packages in configuration.yaml

```yaml
homeassistant:
  packages:
    chores: !include chores/package.yaml
    chores_sensors: !include chores/sensors/chores.yaml
    chores_dinner: !include chores/sensors/dinner.yaml
    chores_rotation: !include chores/automations/rotation.yaml
    chores_weekly_summary: !include chores/automations/weekly_summary.yaml
    chores_dinner_reminder: !include chores/automations/dinner_reminder.yaml
    chores_washer: !include chores/automations/washer_finished.yaml
```

### Step 3: Restart Home Assistant

Settings -> System -> Restart

---

## How It Works

### Chore Rotation
- Every Monday at 00:01, automations rotate all chores to the next person
- Uses `input_datetime.chore_last_rotation` to prevent duplicate rotations (idempotent)
- Each chore's rotation is independent
- State is stored in `input_select` entities (persists across restarts)

### Notifications
- **Daily dinner reminder** at 10:00 - notifies today's cook
- **Weekly chore summary** at 08:00 Monday - each person gets their weekly chores
- **Washer finished** - notifies the current laundry person when washer completes

### Sensors (Always Available)
Template sensors derive from input_selects and are always available, even if automations fail:

- `sensor.chore_laundry` - Current laundry assignee's first name
- `sensor.chore_trash` - Current trash assignee's first name
- `sensor.chore_bathroom` - Current bathroom assignee's first name
- `sensor.chore_plants` - Current plants assignee's first name
- `sensor.chore_cat` - Current cat assignee's first name
- `sensor.chore_outdoor` - Current outdoor assignee's first name
- `sensor.chore_dust` - Current dust assignee's first name
- `sensor.dinner_today` - Today's cook
- `sensor.dinner_tomorrow` - Tomorrow's cook

---

## Manual Control

### Triggering Rotation Manually
Run the automation from Developer Tools -> Services:
```yaml
service: automation.trigger
target:
  entity_id: automation.chores_weekly_rotation
```

### Changing Assignments
Use input_select entities directly via UI or service calls:
```yaml
service: input_select.select_option
target:
  entity_id: input_select.chore_laundry
data:
  option: person.katlyn_otsus
```

---

## Debugging

All automations have traces available in:
Settings -> Automations -> [Automation Name] -> Traces

---

## Modifying Configuration

### Adding/Removing People
1. Update `sensors/chores.yaml` - add/remove from the `names` dict in each sensor
2. Update `sensors/dinner.yaml` - add/remove from the `schedule` dict
3. Update `package.yaml` - add/remove options in input_selects
4. Update automations - adjust rotation lists and notification targets

### Changing Rotation Order
Edit the `rotation` list in `automations/rotation.yaml`.

### Changing Dinner Schedule
Edit `sensors/dinner.yaml` - modify the `schedule` dict.
Edit `automations/dinner_reminder.yaml` - adjust the weekday conditions.
