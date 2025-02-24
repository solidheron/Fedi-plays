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

def send_gameboy_command(pyboy, command, hold_duration=0.35):
    """Send a command to the PyBoy emulator with a delay between button presses."""
    if "*" in command:
        # Command like "a*2" or "left*15"
        button, repetitions = command.split('*')
        repetitions = int(repetitions)  # Convert to integer
        
        # Ensure the repetitions are capped at 10
        if repetitions > 10:
            repetitions = 10

        if button in key_mappings:
            mapped_key = key_mappings[button]
            for _ in range(repetitions):
                pyboy.button_press(mapped_key)
                time.sleep(hold_duration)
                pyboy.button_release(mapped_key)
        else:
            print(f"Invalid button in command: {command}")
    else:
        # Regular command like "a", "left"
        if command in key_mappings:
            mapped_key = key_mappings[command]
            pyboy.button_press(mapped_key)
            time.sleep(hold_duration)
            pyboy.button_release(mapped_key)
        else:
            print(f"Invalid command: {command}")

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

import threading

# Update run_pyboy to return pyboy and pass it to the chat checking
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

async def main():
    # Initialize PyBoy
    print("Initializing PyBoy...")
    rom_path = 'path/to/game.gbc' #put the path to the the gameboy or gameboy color game that you want to play on the emulator
    if not os.path.exists(rom_path):
        print(f"Error: ROM file not found at {rom_path}")
        return

    # Event to stop PyBoy thread gracefully
    stop_event = threading.Event()

    # Thread-safe container for sharing pyboy instance
    pyboy_holder = {}

    # Start PyBoy in a separate thread
    pyboy_thread = threading.Thread(target=run_pyboy, args=(rom_path, stop_event, pyboy_holder))
    pyboy_thread.start()

    # Start checking the chat in a separate task with asyncio
    async with async_playwright() as p:
        try:
            # Launch the browser (use Chromium instead of Firefox)
            browser = await p.chromium.launch(headless=True)  # You can set headless=False for debugging
            print("Chromium browser launched.")

            page = await browser.new_page()
            ##place chat url on page.goto() to read the chat of the peertube stream
            await page.goto("chat url", timeout=60000)  # Timeout after 60 seconds
            print("Page loaded.")

            # Wait for the first message to load
            await page.wait_for_selector('.message', timeout=10000)  # Wait up to 10 seconds for the first message to appear
            print("First message detected, starting the chat checking thread...")

            # Start the chat checking in its own async task
            chat_task = asyncio.create_task(check_chat_messages(page, stop_event, pyboy_holder))

            # Keep both threads running: PyBoy and chat checker
            while pyboy_thread.is_alive():
                await asyncio.sleep(1)  # Prevent the main thread from exiting prematurely

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

    print("Script finished.")

# Run the async main function
asyncio.run(main())

