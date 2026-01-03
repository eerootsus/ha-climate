# Grocy Chore Integration Setup

## What Was Configured

### Grocy Users
| Name | Username | Grocy ID | HA Person ID |
|------|----------|----------|--------------|
| Eero | eero | 1 | person.eero_otsus |
| Kätlyn | katlyn | 2 | person.katlyn_otsus |
| Lola | lola | 3 | person.lola_laur |

### Rotating Chores (Weekly)
| Chore | Grocy ID | HA Sensor | Rotation |
|-------|----------|-----------|----------|
| Pesutoimkond | 3 | sensor.chore_laundry | Eero → Kätlyn → Lola |
| Prügitoimkond | 4 | sensor.chore_trash | Eero → Kätlyn → Lola |
| Tualetitoimkond | 5 | sensor.chore_bathroom | Eero → Kätlyn → Lola |
| Floratoimkond | 6 | sensor.chore_plants | Eero → Kätlyn → Lola |
| Kassitoimkond | 7 | sensor.chore_cat | Eero → Kätlyn → Lola |
| Õuetoimkond | 8 | sensor.chore_outdoor | Eero → Kätlyn |

### Dinner Chores (Fixed)
| Day | Chore | Grocy ID | Assignee |
|-----|-------|----------|----------|
| Monday | Õhtusöök (esmaspäev) | 9 | Kätlyn |
| Tuesday | Õhtusöök (teisipäev) | 10 | Lola |
| Wednesday | Õhtusöök (kolmapäev) | 11 | Eero |
| Thursday | Õhtusöök (neljapäev) | 12 | Lola |
| Friday | Õhtusöök (reede) | 13 | Kätlyn |
| Saturday | Õhtusöök (laupäev) | 14 | Eero |
| Sunday | Õhtusöök (pühapäev) | 15 | Kätlyn |

---

## Home Assistant Setup

### Step 1: Add API Key to secrets.yaml

Add to your `secrets.yaml`:

```yaml
grocy_api_key: "7a0p7BUTT0Wwts1XKwEpxLW0SQBvmNTgnF5w41nhPouXQooIYm"
```

### Step 2: Copy Files to HA Config

Copy the `grocy/` folder to your Home Assistant config directory:

```
config/
├── grocy/                    ← copy this folder
│   ├── package.yaml          # main entry point
│   ├── sensors.yaml          # REST sensors
│   ├── rest_command.yaml     # API commands
│   ├── automations.yaml      # all automations
│   └── dashboard_card.yaml   # dashboard examples
├── configuration.yaml
└── secrets.yaml
```

### Step 3: Include in configuration.yaml

Add the package to your `configuration.yaml`:

```yaml
homeassistant:
  packages:
    grocy: !include grocy/package.yaml
```

### Step 4: Update Notification Service Names

The notification automations use service names like `notify.mobile_app_eero_otsus`.

Check your actual mobile app notification services in **Developer Tools → Services** and update the person_id values in `grocy/package.yaml` if needed.

### Step 5: Restart Home Assistant

After adding the configuration, restart Home Assistant:
- Settings → System → Restart

### Step 6: Add Dashboard Card

1. Go to your dashboard
2. Click **Edit Dashboard** → **Add Card**
3. Choose **Manual** card
4. Paste the card configuration from `grocy/dashboard_card.yaml`

---

## How It Works

### Chore Rotation
- Every Monday at 00:01, the automation executes the 6 rotating chores in Grocy
- This triggers the "in-alphabetical-order" rotation: Eero → Kätlyn → Lola
- The sensors refresh and show the new assignments

### Notifications
- **Daily dinner reminder** at 10:00 - notifies today's cook
- **Weekly chore summary** at 08:00 Monday - each person gets their weekly chores

---

## Modifying the Schedule

### Change Dinner Assignments
1. Go to Grocy → Chores
2. Edit the dinner chore (e.g., "Õhtusöök (esmaspäev)")
3. Change "Next execution assigned to" to the new person
4. Update `chore-config.yaml` with the change

### Change Rotating Chore Participants
To add/remove someone from a chore rotation:
1. Edit the chore in Grocy
2. Update the "Users to cycle through" field
3. Update `chore-config.yaml`

### Regenerate Configuration
If you make significant changes:
1. Update `chore-config.yaml`
2. Ask Claude: "Regenerate my Grocy chore configuration based on chore-config.yaml"

---

## Troubleshooting

### Sensors show "unknown"
- Check that Grocy is accessible from HA
- Verify API key is correct
- Check Developer Tools → States for `sensor.grocy_chores_raw`

### Notifications not working
- Verify mobile app service names in Developer Tools → Services
- Check the automation trace for errors

### Rotation not happening
- Check automation trace for `grocy_weekly_chore_rotation`
- Manually trigger the automation to test
- Verify rest_command is working in Developer Tools → Services
