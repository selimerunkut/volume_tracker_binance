import os
import json
import asyncio
import random
import string
import subprocess
import base64
import argparse # Add argparse
from typing import Optional, Dict, Any

from hummingbot_api_client import HummingbotAPIClient
from aiohttp import ClientResponseError, ClientSession
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Helper Functions ---
def generate_random_string(length=8):
    """Generate a random alphanumeric string."""
    characters = string.ascii_lowercase + string.digits
    return ''.join(random.choice(characters) for i in range(length))

class HummingbotManager:
    def __init__(self, api_base_url: str, api_username: str, api_password: str):
        self.api_base_url = api_base_url
        self.api_username = api_username
        self.api_password = api_password
        self.client = HummingbotAPIClient(api_base_url, api_username, api_password)

        self.session = ClientSession() # Initialize ClientSession here

    async def initialize_client(self):
        """Initializes the HummingbotAPIClient."""
        await self.client.init()

    async def close_client(self):
        """Closes the HummingbotAPIClient and aiohttp session."""
        await self.client.close()
        await self.session.close()

    async def _modify_create_configuration(self, config_name: str, config_params: dict):
        """
        Creates or updates a Hummingbot script configuration.
        """
        print(f"\n--- Modifying/Creating Configuration: {config_name} ---")
        try:
            response = await self.client.scripts.create_or_update_script_config(config_name, config_params)
            print(f"Configuration '{config_name}' saved successfully.")
            print(json.dumps(response, indent=2))
            return True, response
        except ClientResponseError as e:
            print(f"API error occurred: {e.status} - {e.message}")
            print(f"Response content: {await e.text()}")
            return False, {"error": f"API error: {e.status} - {e.message}"}
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return False, {"error": f"Unexpected error: {e}"}

    async def _deploy_v2_script_example(self, instance_name: str, credentials_profile: str, script: str, script_config: Optional[str] = None, image: str = "hummingbot/hummingbot:latest"):
        """
        Deploys a V2 script with a specified configuration and bot name.
        If a container with the same instance_name already exists, it attempts to start it.
        """
        print(f"\n--- Deploying V2 Script: {script} with config {script_config} as bot {instance_name} ---")
        try:
            # Check for active containers
            active_containers = await self.client.docker.get_active_containers(name_filter=instance_name)
            active_container_exists = any(c.get("name") == instance_name for c in active_containers)

            # Check for exited containers
            exited_containers = await self.client.docker.get_exited_containers(name_filter=instance_name)
            exited_container_exists = any(c.get("name") == instance_name for c in exited_containers)

            container_exists = active_container_exists or exited_container_exists

            if container_exists:
                print(f"Container '{instance_name}' already exists (active: {active_container_exists}, exited: {exited_container_exists}).")
                if active_container_exists:
                    print(f"Container '{instance_name}' is active. Attempting to stop and remove it...")
                    try:
                        subprocess.run(["docker", "stop", instance_name], check=True)
                        subprocess.run(["docker", "rm", "-f", instance_name], check=True)
                        print(f"Container '{instance_name}' stopped and removed successfully. Waiting for full removal...")
                        await self._wait_for_container_removal(instance_name)
                        print(f"Container '{instance_name}' fully removed.")
                    except subprocess.CalledProcessError as e:
                        print(f"Error stopping/removing active container: {e}")
                        print("Cannot proceed with deployment as active container cannot be stopped/removed.")
                        return False, {"error": f"Docker error: {e}"}
                elif exited_container_exists:
                    print(f"Container '{instance_name}' is exited. Attempting to remove it...")
                    try:
                        subprocess.run(["docker", "rm", "-f", instance_name], check=True)
                        print(f"Container '{instance_name}' removed successfully.")
                    except subprocess.CalledProcessError as e:
                        print(f"Error removing exited container: {e}")
                        print("Cannot proceed with deployment as exited container cannot be removed.")
                        return False, {"error": f"Docker error: {e}"}
            
            payload = {
                "instance_name": instance_name,
                "credentials_profile": credentials_profile,
                "script": script,
                "image": image,
            }
            if script_config:
                payload["script_config"] = script_config

            response = await self.client.bot_orchestration.deploy_v2_script(**payload)
            print(f"V2 Script '{script}' deployed successfully as bot '{instance_name}'.")
            print(json.dumps(response, indent=2))
            return True, response
        except ClientResponseError as e:
            if e.status == 409:
                print(f"Fallback: Conflict (409) during deployment. Container '{instance_name}' likely exists but wasn't handled.")
                print(f"Attempting to remove and redeploy container '{instance_name}' as a last resort...")
                try:
                    subprocess.run(["docker", "rm", "-f", instance_name], check=True)
                    print(f"Container '{instance_name}' removed successfully.")
                    payload = {
                        "instance_name": instance_name,
                        "credentials_profile": credentials_profile,
                        "script": script,
                        "image": image,
                    }
                    if script_config:
                        payload["script_config"] = script_config
                    response = await self.client.bot_orchestration.deploy_v2_script(**payload)
                    print(f"V2 Script '{script}' deployed successfully after removal as bot '{instance_name}'.")
                    print(json.dumps(response, indent=2))
                    return True, response
                except subprocess.CalledProcessError as fallback_e:
                    print(f"Error during fallback removal/re-deployment: {fallback_e}")
                    return False, {"error": f"Docker fallback error: {fallback_e}"}
            else:
                print(f"API error occurred: {e.status} - {e.message}")
                print(f"Response content: {await e.text()}")
                return False, {"error": f"API error: {e.status} - {e.message}"}
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return False, {"error": f"Unexpected error: {e}"}

    async def _wait_for_container_removal(self, instance_name: str, timeout: int = 60, interval: int = 5):
        """
        Waits until a Docker container is confirmed to be removed.
        """
        start_time = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                subprocess.run(["docker", "inspect", instance_name], check=True, capture_output=True)
                print(f"Container '{instance_name}' still exists. Retrying in {interval} seconds...")
            except subprocess.CalledProcessError as e:
                if "No such object" in e.stderr.decode():
                    return  # Container is removed
                else:
                    raise  # Other error, re-raise
            await asyncio.sleep(interval)
        raise TimeoutError(f"Timeout waiting for container '{instance_name}' to be removed.")

    async def create_and_deploy_bot(self, trading_pair: str, order_amount_usd: float, trailing_stop_loss_delta: float, take_profit_delta: float, fixed_stop_loss_delta: float, credentials_profile: str = "master_account"):
        """
        Creates a Hummingbot configuration and deploys a bot instance.
        """
        config_name = f"config_{generate_random_string(10)}"
        instance_name = f"buy_sell_trailing_stop_bot_{trading_pair.replace('-', '_')}_{generate_random_string(8)}"
        script_name = "buy_sell_trailing_stop.py" # Assuming this is the script name

        config_params = {
            "script_file_name": script_name,
            "connector_name": "binance", # Assuming Binance Perpetual for now
            "trading_pair": trading_pair,
            "order_amount_usd": order_amount_usd,
            "entry_spread": 0.001, # Default value, can be made configurable if needed
            "trailing_stop_loss_delta": trailing_stop_loss_delta,
            "take_profit_delta": take_profit_delta,
            "fixed_stop_loss_delta": fixed_stop_loss_delta,
            "max_active_buy_orders": 1, # Default value, can be made configurable if needed
        }

        print(f"Generated config_name: {config_name}")
        print(f"Generated instance_name: {instance_name}")

        success, config_response = await self._modify_create_configuration(config_name, config_params)
        if not success:
            return False, instance_name, config_response

        success, deploy_response = await self._deploy_v2_script_example(
            instance_name=instance_name,
            credentials_profile=credentials_profile,
            script=script_name,
            script_config=f"{config_name}.yml"
        )
        if not success:
            return False, instance_name, deploy_response

        return True, instance_name, {"config_response": config_response, "deploy_response": deploy_response}

    async def get_bot_status(self, instance_name: str):
        """
        Retrieves the status of a specific bot instance.
        """
        print(f"\n--- Getting Status for Bot Instance: {instance_name} ---")
        try:
            response = await self.client.bot_orchestration.get_bot_status(instance_name)
            print(f"Status for '{instance_name}':")
            #print(json.dumps(response, indent=2))
            return True, response
        except ClientResponseError as e:
            print(f"API error occurred: {e.status} - {e.message}")
            print(f"Response content: {await e.text()}")
            return False, {"error": f"API error: {e.status} - {e.message}"}
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return False, {"error": f"Unexpected error: {e}"}

    async def stop_and_archive_bot(self, instance_name: str, skip_order_cancellation: bool = True, archive_locally: bool = True):
        """
        Stops a running bot instance and archives its data.
        """
        print(f"\n--- Stopping and Archiving Bot Instance: {instance_name} ---")
        try:
            archive_response = await self.client.bot_orchestration.stop_and_archive_bot(
                bot_name=instance_name,
                skip_order_cancellation=skip_order_cancellation,
                archive_locally=archive_locally
            )
            print(f"Bot instance '{instance_name}' archiving process started.")
            print(json.dumps(archive_response, indent=2))
            return True, archive_response
        except ClientResponseError as e:
            print(f"API error occurred: {e.status} - {e.message}")
            print(f"Response content: {await e.text()}")
            return False, {"error": f"API error: {e.status} - {e.message}"}
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return False, {"error": f"Unexpected error: {e}"}

# Example Usage (for testing purposes, can be removed later)
# Main execution block
async def main():
    parser = argparse.ArgumentParser(description="Hummingbot Integration Script")
    parser.add_argument("example_number", type=int, help="Choose an example to run (1-3)")
    parser.add_argument("--config_name", type=str, help="Configuration name for example 1 (not used in this script's examples)")
    parser.add_argument("--instance_name", type=str, help="Instance name for examples 2 and 3")
    args = parser.parse_args()

    load_dotenv()
    api_base_url = os.getenv("HUMMINGBOT_API_URL", "http://localhost:8000")
    api_username = os.getenv("USERNAME")
    api_password = os.getenv("PASSWORD")

    if not all([api_base_url, api_username, api_password]):
        print("Please set HUMMINGBOT_API_URL, USERNAME, and PASSWORD environment variables.")
        return

    manager = HummingbotManager(api_base_url, api_username, api_password)
    await manager.initialize_client() # Initialize the client

    try:
        if args.example_number == 1:
            print("Running Example 1: Create and Deploy a Bot")
            trading_pair_example = "ETH-USDC"
            order_amount_usd_example = 6
            trailing_stop_loss_delta_example = 0.0005
            take_profit_delta_example = 0.0009
            fixed_stop_loss_delta_example = 0.0003
            
            success, instance_name, result = await manager.create_and_deploy_bot(
                trading_pair=trading_pair_example,
                order_amount_usd=order_amount_usd_example,
                trailing_stop_loss_delta=trailing_stop_loss_delta_example,
                take_profit_delta=take_profit_delta_example,
                fixed_stop_loss_delta=fixed_stop_loss_delta_example
            )
            if success:
                print(f"Bot '{instance_name}' created and deployed successfully.")
                print(f"Result: {json.dumps(result, indent=2)}")
            else:
                print(f"Failed to create and deploy bot '{instance_name}'. Error: {result}")
        elif args.example_number == 2:
            print("Running Example 2: Get Bot Status")
            if args.instance_name:
                status_success, status_result = await manager.get_bot_status(args.instance_name)
                if status_success:
                    print(f"Status for '{args.instance_name}': {json.dumps(status_result, indent=2)}")
                else:
                    print(f"Failed to get status for '{args.instance_name}'. Error: {status_result}")
            else:
                print("Error: Please provide --instance_name for example 2.")
        elif args.example_number == 3:
            print("Running Example 3: Stop and Archive Bot")
            if args.instance_name:
                stop_success, stop_result = await manager.stop_and_archive_bot(args.instance_name)
                if stop_success:
                    print(f"Bot '{args.instance_name}' stopped and archived successfully.")
                    print(f"Result: {json.dumps(stop_result, indent=2)}")
                else:
                    print(f"Failed to stop and archive bot '{args.instance_name}'. Error: {stop_result}")
            else:
                print("Error: Please provide --instance_name for example 3.")
        else:
            print("Invalid example number. Please choose 1, 2, or 3.")
    finally:
        await manager.close_client() # Ensure client is closed

if __name__ == "__main__":
    asyncio.run(main())