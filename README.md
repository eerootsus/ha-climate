# Home Assistant Chore Management

Native Home Assistant automations for household chore rotation and notifications.

## What's Configured

### People
| Name | Person Entity | Notification Service |
|------|---------------|---------------------|
| Eero | person.eero_otsus | notify.mobile_app_eeros_iphone_17 |
| Kätlyn | person.katlyn_otsus | notify.mobile_app_katu_iphone |
| Lola | person.lola_laur | notify.mobile_app_lolas_iphone |

### Chores (Random Weekly Distribution, 3 per person)
| Chore | Entity |
|-------|--------|
| Pesutoimkond | input_select.chore_laundry |
| Prügitoimkond | input_select.chore_trash |
| Tualetitoimkond 1. korrus | input_select.chore_bathroom_1 |
| Tualetitoimkond sokkel | input_select.chore_bathroom_basement |
| Floratoimkond | input_select.chore_plants |
| Kassitoimkond | input_select.chore_cat |
| Tolmutoimkond 1. korrus | input_select.chore_dust_1 |
| Tolmutoimkond sokkel | input_select.chore_dust_basement |
| Köögitoimkond | input_select.chore_kitchen |

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
│       ├── cleaning_day.yaml             <- Saturday cleaning day reminder
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
    chores_cleaning_day: !include chores/automations/cleaning_day.yaml
    chores_washer: !include chores/automations/washer_finished.yaml
```

### Step 3: Restart Home Assistant

Settings -> System -> Restart

---

## How It Works

### Chore Distribution
- Every Monday at 00:01, all 9 chores are randomly distributed so each person gets exactly 3
- Uses `input_datetime.chore_last_rotation` to prevent duplicate distributions (idempotent)
- Ada is randomly assigned to help each person with 1 of their 3 chores (3 helper chores total)
- State is stored in `input_select` entities (persists across restarts)

### Notifications
- **Daily dinner reminder** at 10:00 - notifies today's cook
- **Weekly chore summary** at 08:00 Monday - each person gets their weekly chores
- **Cleaning day reminder** at 10:00 Saturday - reminds everyone it's cleaning day with their chores
- **Washer finished** - notifies the current laundry person when washer completes

### Sensors (Always Available)
Template sensors derive from input_selects and are always available, even if automations fail:

- `sensor.chore_laundry` - Current laundry assignee's first name
- `sensor.chore_trash` - Current trash assignee's first name
- `sensor.chore_bathroom_1` - Current 1st floor bathroom assignee's first name
- `sensor.chore_bathroom_basement` - Current basement bathroom assignee's first name
- `sensor.chore_plants` - Current plants assignee's first name
- `sensor.chore_cat` - Current cat assignee's first name
- `sensor.chore_dust_1` - Current 1st floor dust assignee's first name
- `sensor.chore_dust_basement` - Current basement dust assignee's first name
- `sensor.chore_kitchen` - Current kitchen assignee's first name
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

### Changing Distribution
Edit the chore and people lists in `automations/rotation.yaml`.

### Changing Dinner Schedule
Edit `sensors/dinner.yaml` - modify the `schedule` dict.
Edit `automations/dinner_reminder.yaml` - adjust the weekday conditions.

---

## E-Ink Theme

Custom theme optimized for e-ink displays with serif fonts and larger text.

### Installation

1. Copy `themes/eink-serif.yaml` to your HA config:
   ```
   config/
   └── themes/
       └── eink-serif.yaml
   ```

2. Add to `configuration.yaml`:
   ```yaml
   frontend:
     themes: !include_dir_merge_named themes
   ```

3. Reload themes: Developer Tools -> YAML -> Themes

4. Select theme: Profile -> Theme -> eink-serif

### card-mod Tweaks (requires [card-mod](https://github.com/thomasloven/lovelace-card-mod))

Weather card:
```yaml
card_mod:
  style: |
    .temp-attribute .temp {
      margin-right: 36px !important;
      line-height: 32px !important;
      font-weight: 700;
    }
    .temp-attribute .temp span {
      font-weight: 400;
    }
    .name-state .name {
      display: none;
    }
```

Chores entities card:
```yaml
card_mod:
  style: |
    .card-header {
      font-weight: 700;
    }
    #states {
      font-size: 18px;
    }
```
