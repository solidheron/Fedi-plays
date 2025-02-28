import os
import re
import unicodedata
import hashlib
import time
import threading
import asyncio
from pyboy import PyBoy
from playwright.async_api import async_playwright, TimeoutError

# PyBoy key mappings
key_mappings = {
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "start": "start",
    "select": "select",
    "a": "a",
    "b": "b",
}

last_release_time = time.time()

def release_all_buttons(pyboy):
    """Release all buttons if any are currently pressed."""
    for button in key_mappings.values():
        pyboy.button_release(button)
    #print("All buttons released.")

def send_gameboy_command(pyboy, command, hold_duration=0.35):
    """Send a command to the PyBoy emulator with a delay between button presses, and release all buttons every hour."""
    global last_release_time  # Track the time of the last button release
    release_all_buttons(pyboy)

    # Get the current time
    current_time = time.time()
    
    # Check if an hour has passed since the last button release
    if current_time - last_release_time >= 7:  # 3600 seconds = 1 hour
        #print("Releasing all buttons")
        #release_all_buttons(pyboy)
        last_release_time = current_time  # Update the last release time

    # List to keep track of buttons that are pressed
    pressed_buttons = []

    try:
        # If "*" is in the command, handle repeated presses like "a*2" or "left*15"
        if "*" in command:
            button, repetitions = command.split('*')
            repetitions = int(repetitions)  # Convert to integer
            
            # Ensure the repetitions are capped at 10
            if repetitions > 10:
                repetitions = 10

            if button in key_mappings:
                mapped_key = key_mappings[button]
                for _ in range(repetitions):
                    pyboy.button_press(mapped_key)
                    pressed_buttons.append(mapped_key)  # Track the button pressed
                    time.sleep(hold_duration)  # Hold the button for the specified duration
                    pyboy.button_release(mapped_key)  # Immediately release the button after press
                    time.sleep(0.1)  # Optional small delay between presses
            else:
                print(f"Invalid button in command: {command}")
        else:
            # Regular command like "a", "left"
            if command in key_mappings:
                mapped_key = key_mappings[command]
                pyboy.button_press(mapped_key)
                pressed_buttons.append(mapped_key)  # Track the button pressed
                time.sleep(hold_duration)  # Hold the button for the specified duration
                pyboy.button_release(mapped_key)  # Release the button after the delay
                time.sleep(0.1)  # Optional small delay between releases
            else:
                print(f"Invalid command: {command}")

    finally:
        # Ensure all buttons are released at the end (safety)
        for button in pressed_buttons:
            pyboy.button_release(button)
            release_all_buttons(pyboy)
            time.sleep(0.1)  # Optional small delay between releasing buttons to avoid sticking




def save_state(pyboy, save_file):
    """Save the current state of the PyBoy emulator."""
    try:
        # Ensure the directory exists
        save_dir = os.path.dirname(save_file)
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)

        # Open the file in write-binary mode and save the state
        with open(save_file, 'wb') as f:
            pyboy.save_state(f)
    except Exception as e:
        print(f"Error saving state: {e}")

def load_state(pyboy, save_file):
    """Load the saved state into the PyBoy emulator."""
    try:
        if os.path.exists(save_file):
            with open(save_file, 'rb') as f:
                pyboy.load_state(f)
        else:
            print(f"No saved state found at {save_file}, starting fresh.")
    except Exception as e:
        print(f"Error loading state: {e}")

def run_pyboy(rom_path, stop_event, pyboy_holder, save_interval=1800):
    """Run the PyBoy emulator in a separate thread and share the instance."""
    pyboy = PyBoy(rom_path)
    
    # Load the saved state
    save_file = './pyboy_saves/state.sav'  # Relative path in the current directory
    load_state(pyboy, save_file)

    pyboy.set_emulation_speed(1)  # Adjust emulation speed (1 is default, higher is faster)
    pyboy_holder['pyboy'] = pyboy  # Store the pyboy instance in a thread-safe container (dict)
    
    last_save_time = time.time()

    try:
        while not stop_event.is_set():  # Run until the event is set
            pyboy.tick()  # Advance the game state
            time.sleep(0.01)  # Adjust to control the emulation frame rate
            
            # Save state every `save_interval` seconds
            current_time = time.time()
            if current_time - last_save_time >= save_interval:
                save_state(pyboy, save_file)
                last_save_time = current_time  # Update last save time
                
    except Exception as e:
        print(f"Error in PyBoy thread: {e}")
    finally:
        pyboy.stop()

async def get_latest_message_from_chat(page):
    """Get the latest message from the chat using Playwright."""
    await page.wait_for_selector('.message', state='attached')  # Ensure the message is present
    message_element = page.locator('.message').last  # Get the last message
    return await message_element.text_content()  # Make sure to await the text content

async def check_chat_messages(page, stop_event, pyboy_holder):
    """Function to check chat messages at regular intervals."""
    last_username, last_timestamp, last_content = None, None, None

    while not stop_event.is_set():
        try:
            # Get the latest message from the chat
            message_content = await get_latest_message_from_chat(page)

            # Skip if message contains "This groupchat is not anonymous"
            if "This groupchat is not anonymous" in message_content:
                continue

            # Adjusted regex to handle the provided message structure with extra spaces
            message_content = message_content.strip()

            # Updated regex to handle multiple spaces and capture the correct parts
            match = re.match(r"(\S+)\s+(\d{1,2}:\d{2})\s+(\S+)", message_content)

            if match:
                username = match.group(1)  # Extract the username
                timestamp = match.group(2)  # Extract the timestamp
                command = match.group(3)    # Extract the first command (e.g., Start)

                # Normalize command (convert to lowercase, strip extra spaces)
                normalized_command = unicodedata.normalize("NFKC", command.lower().strip())
                normalized_command = normalized_command.replace("\xa0", " ")
                normalized_command = " ".join(normalized_command.split())

                # Create a hash of the entire message to track uniqueness
                message_hash = hashlib.md5(f"{username}{timestamp}{normalized_command}".encode()).hexdigest()

                # Skip if this message has already been processed
                if message_hash == last_content:
                    continue

                # Update the last processed message
                last_username = username
                last_timestamp = timestamp
                last_content = message_hash

                # Process commands based on the message
                print(f"Decision: Command '{normalized_command}' triggered based on message: {normalized_command}")
                # Access the pyboy instance from pyboy_holder dictionary
                pyboy = pyboy_holder.get('pyboy')
                if pyboy:
                    send_gameboy_command(pyboy, normalized_command)
                else:
                    print("Error: PyBoy instance not found!")

                # Output the message and command being processed
                print(f"Latest Message:")
                print(f"Username: {username}")
                print(f"Timestamp: {timestamp}")
                print(f"Command: {normalized_command}")
                print("---")
            else:
                print(f"Failed to match message: {message_content}")
        
        except Exception as e:
            print(f"Error processing message: {e}")

        # Wait before checking for new messages again
        await asyncio.sleep(4)

async def run_asyncio_tasks():
    """Run the async tasks."""
    async with async_playwright() as p:
        try:
            # Launch the browser in headless mode or not based on your needs
            browser = await p.chromium.launch(headless=False)  # Try headless=False for debugging
            print("Chromium browser launched.")

            page = await browser.new_page()
            await page.goto("https://dalek.zone/plugins/livechat/router/webchat/room/80fc8497-dc83-4f75-b961-120de17716c2#?p=pi6fnM7QuiXlYQu5DOjRWeX105fljH&j=solidheron%40dalek.zone&n=solidheron", timeout=60000)
            print("Page loaded.")

            # Wait for the first message to load
            await page.wait_for_selector('.message', timeout=10000)  # Wait for the first message to appear
            print("First message detected, starting the chat checking thread...")

            # Create the task for checking chat messages
            chat_task = asyncio.create_task(check_chat_messages(page, stop_event, pyboy_holder))

            # Run the loop to allow asyncio tasks to run
            await chat_task  # Ensure chat task completes
            
        except TimeoutError:
            print("Error: Timed out while waiting for the page to load or the first message.")
        except Exception as e:
            print(f"Error during Playwright execution: {e}")
        finally:
            # Ensure the browser is closed when done
            print("Closing browser...")
            await browser.close()

            # Stop the threads gracefully
            stop_event.set()
            pyboy_thread.join()

def start_asyncio_in_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_asyncio_tasks())  # Ensure asyncio tasks run here

# Event to stop PyBoy thread gracefully
stop_event = threading.Event()

# Thread-safe container for sharing pyboy instance
pyboy_holder = {}

# Run asyncio tasks in a separate thread
asyncio_thread = threading.Thread(target=start_asyncio_in_thread)
asyncio_thread.start()

# Start PyBoy in a separate thread
rom_path = '/path/to/rom.gbc'
pyboy_thread = threading.Thread(target=run_pyboy, args=(rom_path, stop_event, pyboy_holder))
pyboy_thread.start()

