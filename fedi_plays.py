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
    """
    Send a command to the PyBoy emulator with a delay between button presses,
    and release all buttons every hour.
    
    Supports commands like "up*4" or "up 4" to simulate multiple presses.
    """
    global last_release_time  # Track the time of the last button release
    release_all_buttons(pyboy)

    current_time = time.time()
    # Check if an hour has passed since the last button release (here set to 7 seconds for testing)
    if current_time - last_release_time >= 7:
        #print("Releasing all buttons")
        last_release_time = current_time

    pressed_buttons = []

    try:
        repetitions = 1  # default is a single press

        # Check for both formats: "button*reps" or "button reps"
        if "*" in command:
            parts = command.split('*')
            if len(parts) == 2:
                button, reps_str = parts
                try:
                    repetitions = int(reps_str)
                except ValueError:
                    print(f"Invalid repetition count in command: {command}")
                    return
            else:
                print(f"Invalid command format: {command}")
                return
        elif " " in command:
            parts = command.split()
            if len(parts) == 2 and parts[1].isdigit():
                button = parts[0]
                repetitions = int(parts[1])
            else:
                button = command  # Fallback to the entire command if not matching expected format
        else:
            button = command

        # Cap repetitions at 10
        if repetitions > 15:
            repetitions = 15

        if button in key_mappings:
            mapped_key = key_mappings[button]
            for _ in range(repetitions):
                pyboy.button_press(mapped_key)
                pressed_buttons.append(mapped_key)
                time.sleep(hold_duration)
                pyboy.button_release(mapped_key)
                time.sleep(0.05)
        else:
            print(f"Invalid command/button: {command}")

    finally:
        for button in pressed_buttons:
            pyboy.button_release(button)
        release_all_buttons(pyboy)
        #time.sleep(0.05)

def save_state(pyboy, save_file):
    """Save the current state of the PyBoy emulator."""
    try:
        save_dir = os.path.dirname(save_file)
        if not os.path.exists(save_dir):
            os.makedirs(save_dir)
        with open(save_file, 'wb') as f:
            pyboy.save_state(f)
    except Exception as e:
        print(f"Error saving state: {e}")

def load_state(pyboy, save_file):
    if os.path.exists(save_file):
        try:
            if os.path.getsize(save_file) < 100:
                raise ValueError("Save file appears corrupted")
            with open(save_file, 'rb') as f:
                pyboy.load_state(f)
                for _ in range(10):
                    pyboy.tick()
        except Exception as e:
            print(f"Failed to load state: {e}")
            os.remove(save_file)
            print("Removed corrupted save file")

def run_pyboy(rom_path, stop_event, pyboy_holder, save_interval=30*60):
    pyboy = PyBoy(rom_path)
    for _ in range(60):
        pyboy.tick()
    
    save_file = './pyboy_saves/state.sav'
    load_state(pyboy, save_file)
    pyboy_holder['pyboy'] = pyboy

    last_save_time = time.time()

    try:
        while not stop_event.is_set():
            pyboy.tick()
            time.sleep(0.01)
            if time.time() - last_save_time >= save_interval:
                save_state(pyboy, save_file)
                last_save_time = time.time()
    except Exception as e:
        print(f"Error in PyBoy thread: {e}")
    finally:
        pyboy.stop()

async def get_latest_message_from_chat(page):
    """Get the latest message from the chat using Playwright."""
    await page.wait_for_selector('.message', state='attached')
    message_element = page.locator('.message').last
    return await message_element.text_content()

async def get_last_5_messages_from_chat(page):
    """Get the last 5 messages from the chat using Playwright."""
    await page.wait_for_selector('.message', state='attached')
    message_elements = page.locator('.message')
    count = await message_elements.count()
    
    messages = []
    for i in range(max(0, count - 5), count):
        element = message_elements.nth(i)
        messages.append(await element.text_content())
    return messages


async def check_chat_messages(page, stop_event, pyboy_holder):
    """Check chat messages at regular intervals."""
    last_username, last_timestamp, last_content = None, None, None
    username_map = {}
    previous_last_5_message_content = await get_last_5_messages_from_chat(page) #gets the last 5 messages
    valid_commands = {"up", "down", "left", "right", "a", "b", "start", "select"}
    pyboy = pyboy_holder.get('pyboy')

    while not stop_event.is_set():
        try:
            
            last_5_message_content = await get_last_5_messages_from_chat(page) #gets the last 5 messages
            release_all_buttons(pyboy)
            if (previous_last_5_message_content == last_5_message_content):
                await asyncio.sleep(2)
                continue
            
            message_content = await get_latest_message_from_chat(page)

            if "This groupchat is not anonymous" in message_content:
                continue
            if "Your nickname has been changed to" in message_content:
                if "LaNiDoNa Media" in message_content:
                    print(f"Ignoring nickname change: {message_content}")
                    continue

            message_content = message_content.strip()
            if ":" in message_content:
                match = re.match(r"([^\s]+(?: [^\s]+)*)\s*(\d{1,2}:\d{2})\s*(\S+.*)?", message_content)
                if match:
                    username = match.group(1)
                    timestamp = match.group(2)
                    command = match.group(3)
                    if command is None:
                        continue
                else:
                    username = "unknown"
                    timestamp = None
                    command = message_content
            else:
                username = "unknown"
                timestamp = None
                command = message_content

            original_command = command.strip()
            # Normalize the command (this preserves original capitalization).
            normalized = unicodedata.normalize("NFKC", original_command)
            normalized = normalized.replace("\xa0", " ")
            normalized = " ".join(normalized.split())

            # Create a lower-case version solely for validation purposes.
            lower_command = normalized.lower()

            # Convert a command like "a4" or "A4" into "a*4" if it matches the letter+digit pattern.
            match = re.match(r"^([a-z]+)(\d+)$", lower_command)
            if match:
                # Use the lower-case letters from the match since key_mappings are lower-case.
                converted = f"{match.group(1)}*{match.group(2)}"
                # Only convert if the letter part is a valid command.
                if match.group(1) in key_mappings:
                    normalized = converted

            # Now split tokens from the normalized (converted) command.
            tokens = normalized.split()
            base_command = tokens[0] if tokens else ""
            repetitions = 1

            if len(tokens) > 1 and tokens[1].isdigit():
                repetitions = int(tokens[1])

            # Validate using lower-case conversion for the base command.
            base_command1 = base_command
            base_command = base_command.lower()
            if base_command.lower() not in valid_commands:
                #print(f"Invalid command: {normalized}")
                continue  # Skip this message

            # At this point, the command is valid and processed.
            #print(base_command.lower())
            normalized_command = f"{base_command}*{repetitions}" if repetitions > 1 else base_command

            # (Proceed with duplicate detection and further processing using 'normalized_command')
            message_hash = hashlib.md5(f"{username}{timestamp}{normalized_command}".encode()).hexdigest()
            if message_hash == last_content:
                #continue
                print("message hash match")

            last_username = username
            last_timestamp = timestamp
            last_content = message_hash

            print(f"Decision: Command '{normalized_command}' triggered based \non message: {base_command1}")
            #pyboy = pyboy_holder.get('pyboy')
            if  pyboy:
                send_gameboy_command(pyboy, normalized_command)
            else:
                print("Error: PyBoy instance not found!")
            #print(f"Latest Message: {original_command}")
            print(f"Username: {username}")
            print(f"Timestamp: {timestamp}")
            print(f"Command: {normalized_command}")
            #print("---")
            #print("Last 5 Messages:")  # Print the last 5 messages for debugging
            #for msg in last_5_message_content:
                #print(f"- {msg}")
            print("---")

        except Exception as e:
            print(f"Error processing message: {e}")
            await page.reload()
            print("Page refreshed.")
        previous_last_5_message_content = last_5_message_content
        #await asyncio.sleep(1)

async def run_asyncio_tasks():
    """Run the async tasks."""
    async with async_playwright() as p:
        browser = None
        try:
            browser = await p.firefox.launch(headless=False)
            print("Firefox browser launched.")
            page = await browser.new_page()
            await page.goto("https://put.your/chaturl/here", timeout=60000)
            print("Page loaded.")
            await page.wait_for_selector('.message', timeout=60000)
            print("First message detected, starting the chat checking thread...")
            chat_task = asyncio.create_task(check_chat_messages(page, stop_event, pyboy_holder))
            await chat_task

            # Refresh the page after the chat task completes
            await page.reload()
            print("Page refreshed.")

        except TimeoutError:
            print("Error: Timed out while waiting for the page or message.")
        except Exception as e:
            print(f"Error during Playwright execution: {e}")
        finally:
            if browser:
                print("Closing browser...")
                await browser.close()
            stop_event.set()
            pyboy_thread.join()

def start_asyncio_in_thread():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_asyncio_tasks())

# Event to stop threads gracefully
stop_event = threading.Event()
pyboy_holder = {}

# Start asyncio tasks in a separate thread
asyncio_thread = threading.Thread(target=start_asyncio_in_thread)
asyncio_thread.start()

# Start PyBoy in a separate thread
rom_path = r'./GB_set/Dragon Warrior Monsters.gbc'
pyboy_thread = threading.Thread(target=run_pyboy, args=(rom_path, stop_event, pyboy_holder))
pyboy_thread.start()

# Main thread listens for a keyboard interrupt for graceful shutdown
try:
    while asyncio_thread.is_alive() and pyboy_thread.is_alive():
        time.sleep(1)
except KeyboardInterrupt:
    print("KeyboardInterrupt received. Initiating graceful shutdown...")
    stop_event.set()
finally:
    asyncio_thread.join()
    pyboy_thread.join()
    print("Shutdown complete.")
