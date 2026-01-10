"""
Chore management system for Home Assistant using pyscript.

Handles:
- Weekly rotation of household chores
- Daily dinner reminders
- Weekly chore summary notifications
"""

# People configuration - maps person entity IDs to notification services and names
PEOPLE = {
    "person.eero_otsus": {"notify": "mobile_app_fp5", "first_name": "Eero"},
    "person.katlyn_otsus": {"notify": "mobile_app_katu_iphone", "first_name": "Kätlyn"},
    "person.lola_laur": {"notify": None, "first_name": "Lola"},
}

# Rotating chores configuration
ROTATING_CHORES = [
    {
        "entity": "input_select.chore_laundry",
        "name": "Pesutoimkond",
        "rotation": ["person.eero_otsus", "person.katlyn_otsus", "person.lola_laur"],
    },
    {
        "entity": "input_select.chore_trash",
        "name": "Prügitoimkond",
        "rotation": ["person.eero_otsus", "person.katlyn_otsus", "person.lola_laur"],
    },
    {
        "entity": "input_select.chore_bathroom",
        "name": "Tualetitoimkond",
        "rotation": ["person.eero_otsus", "person.katlyn_otsus", "person.lola_laur"],
    },
    {
        "entity": "input_select.chore_plants",
        "name": "Floratoimkond",
        "rotation": ["person.eero_otsus", "person.katlyn_otsus", "person.lola_laur"],
    },
    {
        "entity": "input_select.chore_cat",
        "name": "Kassitoimkond",
        "rotation": ["person.eero_otsus", "person.katlyn_otsus", "person.lola_laur"],
    },
    {
        "entity": "input_select.chore_outdoor",
        "name": "Õuetoimkond",
        "rotation": ["person.eero_otsus", "person.katlyn_otsus"],
    },
    {
        "entity": "input_select.chore_dust",
        "name": "Tolmutoimkond",
        "rotation": ["person.eero_otsus", "person.katlyn_otsus", "person.lola_laur"],
    },
]

# Dinner schedule - weekday (0=Monday) to person entity ID
DINNER_SCHEDULE = {
    0: "person.katlyn_otsus",  # Monday
    1: "person.lola_laur",        # Tuesday
    2: "person.eero_otsus",       # Wednesday
    3: "person.lola_laur",        # Thursday
    4: "person.katlyn_otsus",  # Friday
    5: "person.eero_otsus",       # Saturday
    6: "person.katlyn_otsus",  # Sunday
}


def get_person_name(person_id):
    """Get friendly name from a person entity ID."""
    attrs = state.getattr(person_id)
    if attrs and "friendly_name" in attrs:
        return attrs["friendly_name"]
    # Fallback: extract name from entity ID
    return person_id.split(".")[-1].replace("_", " ").title()


def get_first_name(person_id):
    """Get first name for a person entity ID."""
    person_config = PEOPLE.get(person_id, {})
    if "first_name" in person_config:
        return person_config["first_name"]
    # Fallback: extract from entity ID
    return person_id.split(".")[-1].split("_")[0].title()


def get_notify_service(person_id):
    """Get the notification service for a person."""
    person_config = PEOPLE.get(person_id, {})
    notify = person_config.get("notify")
    if notify:
        return f"notify.{notify}"
    return None


@time_trigger("cron(1 0 * * 1)")  # Monday at 00:01
def rotate_chores():
    """Rotate all chores to the next person in rotation."""
    log.info("Starting weekly chore rotation")

    for chore in ROTATING_CHORES:
        entity = chore["entity"]
        rotation = chore["rotation"]

        # Get current assignee
        current = state.get(entity)

        if current in rotation:
            # Find next person in rotation
            current_index = rotation.index(current)
            next_index = (current_index + 1) % len(rotation)
            next_person = rotation[next_index]
        else:
            # Current assignee not in rotation, start from first
            next_person = rotation[0]

        # Update the input_select
        input_select.select_option(entity_id=entity, option=next_person)
        log.info(f"Rotated {chore['name']}: {get_person_name(current)} -> {get_person_name(next_person)}")

    log.info("Weekly chore rotation complete")


@time_trigger("cron(0 10 * * *)")  # Daily at 10:00
def send_dinner_reminder():
    """Send dinner reminder to today's cook."""
    import datetime

    weekday = datetime.datetime.now().weekday()
    person_id = DINNER_SCHEDULE.get(weekday)

    if not person_id:
        log.warning(f"No dinner assignment for weekday {weekday}")
        return

    notify_service = get_notify_service(person_id)
    if not notify_service:
        log.info(f"No notification service for {get_person_name(person_id)}, skipping dinner reminder")
        return

    person_name = get_person_name(person_id)
    log.info(f"Sending dinner reminder to {person_name}")

    service.call(
        notify_service.split(".")[0],
        notify_service.split(".")[1],
        title="Köögitoimkond",
        message="Sina oled täna õhtusöögi tegija!",
    )


@time_trigger("cron(0 8 * * 1)")  # Monday at 08:00
def send_weekly_summary():
    """Send weekly chore summary to each person."""
    log.info("Sending weekly chore summaries")

    # Build chore assignments per person
    person_chores = {person_id: [] for person_id in PEOPLE}

    for chore in ROTATING_CHORES:
        entity = chore["entity"]
        current = state.get(entity)

        if current in person_chores:
            person_chores[current].append(chore["name"])

    # Send notifications
    for person_id, chores in person_chores.items():
        notify_service = get_notify_service(person_id)
        if not notify_service:
            log.info(f"No notification service for {get_person_name(person_id)}, skipping summary")
            continue

        if not chores:
            log.info(f"No chores assigned to {get_person_name(person_id)} this week")
            continue

        person_name = get_person_name(person_id)
        chore_list = ", ".join(chores)

        log.info(f"Sending weekly summary to {person_name}: {chore_list}")

        service.call(
            notify_service.split(".")[0],
            notify_service.split(".")[1],
            title="Nädala toimkonnad",
            message=f"Sinu toimkonnad sel nädalal: {chore_list}",
        )

    log.info("Weekly chore summaries sent")


@service
def chores_rotate_now():
    """Service to manually trigger chore rotation."""
    rotate_chores()


@service
def chores_send_summaries():
    """Service to manually trigger weekly summary notifications."""
    send_weekly_summary()


@service
def chores_send_dinner_reminder():
    """Service to manually trigger dinner reminder."""
    send_dinner_reminder()


# Sensor configuration - maps chore entity to sensor details
CHORE_SENSORS = {
    "input_select.chore_laundry": {"sensor": "sensor.chore_laundry", "name": "Chore Laundry", "icon": "mdi:washing-machine"},
    "input_select.chore_trash": {"sensor": "sensor.chore_trash", "name": "Chore Trash", "icon": "mdi:trash-can"},
    "input_select.chore_bathroom": {"sensor": "sensor.chore_bathroom", "name": "Chore Bathroom", "icon": "mdi:toilet"},
    "input_select.chore_plants": {"sensor": "sensor.chore_plants", "name": "Chore Plants", "icon": "mdi:flower"},
    "input_select.chore_cat": {"sensor": "sensor.chore_cat", "name": "Chore Cat", "icon": "mdi:cat"},
    "input_select.chore_outdoor": {"sensor": "sensor.chore_outdoor", "name": "Chore Outdoor", "icon": "mdi:tree"},
    "input_select.chore_dust": {"sensor": "sensor.chore_dust", "name": "Chore Dust", "icon": "mdi:vacuum"},
}


def update_chore_sensors():
    """Update all chore sensors with the current assignee's first name."""
    for input_entity, sensor_config in CHORE_SENSORS.items():
        person_id = state.get(input_entity)
        first_name = get_first_name(person_id)
        state.set(
            sensor_config["sensor"],
            first_name,
            friendly_name=sensor_config["name"],
            icon=sensor_config["icon"],
            person_id=person_id,
        )


def update_dinner_sensors():
    """Update dinner sensors with the cook's first name."""
    import datetime

    today = datetime.datetime.now().weekday()
    tomorrow = (today + 1) % 7

    today_person = DINNER_SCHEDULE.get(today)
    tomorrow_person = DINNER_SCHEDULE.get(tomorrow)

    state.set(
        "sensor.dinner_today",
        get_first_name(today_person),
        friendly_name="Dinner Today",
        icon="mdi:silverware-fork-knife",
        person_id=today_person,
    )
    state.set(
        "sensor.dinner_tomorrow",
        get_first_name(tomorrow_person),
        friendly_name="Dinner Tomorrow",
        icon="mdi:silverware-fork-knife",
        person_id=tomorrow_person,
    )


@time_trigger("startup")
def initialize_sensors():
    """Initialize all sensors on startup."""
    log.info("Initializing chore and dinner sensors")
    update_chore_sensors()
    update_dinner_sensors()


@state_trigger("input_select.chore_laundry, input_select.chore_trash, input_select.chore_bathroom, input_select.chore_plants, input_select.chore_cat, input_select.chore_outdoor, input_select.chore_dust")
def on_chore_change():
    """Update chore sensors when any input_select changes."""
    update_chore_sensors()


@state_trigger("sensor.washer_washer_job_state == 'finish'")
def on_washer_finished():
    """Notify laundry person when washer finishes."""
    person_id = state.get("input_select.chore_laundry")
    notify_service = get_notify_service(person_id)

    if not notify_service:
        log.info(f"No notification service for {get_person_name(person_id)}, skipping washer notification")
        return

    log.info(f"Sending washer finished notification to {get_person_name(person_id)}")

    service.call(
        notify_service.split(".")[0],
        notify_service.split(".")[1],
        title="Pesutoimkond",
        message="Pesumasin lõpetas!",
    )


@time_trigger("cron(0 0 * * *)")  # Daily at midnight
def update_dinner_daily():
    """Update dinner sensors daily."""
    update_dinner_sensors()
