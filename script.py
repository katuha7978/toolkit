import logging
import time
import json
import os
from web3 import Web3
from web3.middleware import geth_poa_middleware
from requests.exceptions import RequestException
import requests

# --- Configuration ---
# In a real-world application, this would be loaded from a secure configuration service or a .env file.
CONFIG = {
    'source_chain': {
        'name': 'SourceChain-Goerli',
        'rpc_url': 'https://goerli.infura.io/v3/YOUR_INFURA_PROJECT_ID', # Replace with your RPC URL
        'bridge_contract_address': '0x...',
        'bridge_contract_abi': '[]' # Replace with actual ABI
    },
    'destination_chain': {
        'name': 'DestinationChain-Mumbai',
        'rpc_url': 'https://polygon-mumbai.infura.io/v3/YOUR_INFURA_PROJECT_ID', # Replace with your RPC URL
        'bridge_contract_address': '0x...',
    },
    'listener': {
        'poll_interval_seconds': 15, # Time to wait between polling for new blocks
        'start_block': 'latest', # Or a specific block number to start from
        'db_file': 'processed_events.json' # Simple file-based DB to track state
    },
    'gas_oracle_api': 'https://api.etherscan.io/api?module=gastracker&action=gasoracle&apikey=YourApiKeyToken'
}

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(levelname)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


class StateDB:
    """
    A simple file-based database to persist the state of processed events.
    This prevents processing the same event twice upon listener restart.
    In a production system, this would be a more robust database like Redis or PostgreSQL.
    """

    def __init__(self, db_file_path):
        """Initializes the StateDB instance.

        Args:
            db_file_path (str): The path to the JSON file used for storage.
        """
        self.db_file_path = db_file_path
        self.processed_txs = self._load()
        logging.info(f"StateDB initialized. Loaded {len(self.processed_txs)} processed transaction hashes from '{db_file_path}'.")

    def _load(self):
        """Loads the set of processed transaction hashes from the file."""
        if not os.path.exists(self.db_file_path):
            return set()
        try:
            with open(self.db_file_path, 'r') as f:
                data = json.load(f)
                return set(data.get('processed_txs', []))
        except (json.JSONDecodeError, IOError) as e:
            logging.error(f"Error loading state DB file '{self.db_file_path}': {e}. Starting with an empty state.")
            return set()

    def _save(self):
        """Saves the current set of processed transaction hashes to the file."""
        try:
            with open(self.db_file_path, 'w') as f:
                json.dump({'processed_txs': list(self.processed_txs)}, f, indent=4)
        except IOError as e:
            logging.error(f"Could not save state to DB file '{self.db_file_path}': {e}")

    def is_processed(self, tx_hash):
        """Checks if a given transaction hash has already been processed.

        Args:
            tx_hash (str): The transaction hash to check.

        Returns:
            bool: True if processed, False otherwise.
        """
        return tx_hash in self.processed_txs

    def mark_as_processed(self, tx_hash):
        """Marks a transaction hash as processed and saves the state.

        Args:
            tx_hash (str): The transaction hash to mark.
        """
        self.processed_txs.add(tx_hash)
        self._save()
        logging.info(f"Transaction {tx_hash} marked as processed.")


class BlockchainConnector:
    """
    Handles the connection to a single blockchain node via Web3.py.
    Encapsulates the logic for fetching blocks and contract instances.
    """

    def __init__(self, name, rpc_url, contract_address=None, contract_abi=None):
        """Initializes the connector.

        Args:
            name (str): A human-readable name for the chain (e.g., 'Goerli').
            rpc_url (str): The HTTP RPC endpoint URL for the blockchain node.
            contract_address (str, optional): The address of the target contract.
            contract_abi (str, optional): The ABI of the target contract as a JSON string.
        """
        self.name = name
        self.web3 = Web3(Web3.HTTPProvider(rpc_url))
        # Middleware for PoA chains like Polygon Mumbai or Goerli
        self.web3.middleware_onion.inject(geth_poa_middleware, layer=0)

        if not self.web3.is_connected():
            raise ConnectionError(f"Failed to connect to blockchain node at {rpc_url}")

        logging.info(f"Successfully connected to {self.name} at {rpc_url}. Chain ID: {self.web3.eth.chain_id}")

        self.contract = None
        if contract_address and contract_abi:
            try:
                # A mock ABI for demonstration purposes.
                # In a real system, this would be the actual, complex bridge contract ABI.
                mock_abi = '''
                [
                    {
                        "anonymous": false,
                        "inputs": [
                            {"indexed": true, "name": "from", "type": "address"},
                            {"indexed": true, "name": "toChainId", "type": "uint256"},
                            {"indexed": false, "name": "amount", "type": "uint256"},
                            {"indexed": false, "name": "token", "type": "address"}
                        ],
                        "name": "TokensLocked",
                        "type": "event"
                    }
                ]
                '''
                self.contract = self.web3.eth.contract(
                    address=Web3.to_checksum_address(contract_address),
                    abi=mock_abi
                )
                logging.info(f"Contract object created for address {contract_address} on {self.name}.")
            except Exception as e:
                 logging.error(f"Failed to create contract instance: {e}")
                 raise

    def get_latest_block_number(self):
        """Fetches the latest block number from the connected node."""
        try:
            return self.web3.eth.block_number
        except Exception as e:
            logging.error(f"Failed to get latest block number from {self.name}: {e}")
            return None


class CrossChainEventListener:
    """
    The main orchestrator class.
    It connects to the source chain, listens for specific events, processes them,
    and simulates triggering actions on the destination chain.
    """

    def __init__(self, config):
        """Initializes the event listener with the provided configuration."""
        self.config = config
        self.source_connector = BlockchainConnector(
            name=config['source_chain']['name'],
            rpc_url=config['source_chain']['rpc_url'],
            contract_address=config['source_chain']['bridge_contract_address'],
            contract_abi=config['source_chain']['bridge_contract_abi']
        )
        self.destination_connector = BlockchainConnector(
            name=config['destination_chain']['name'],
            rpc_url=config['destination_chain']['rpc_url']
        )
        self.state_db = StateDB(config['listener']['db_file'])
        self.last_processed_block = self._get_start_block()
        self.poll_interval = config['listener']['poll_interval_seconds']

    def _get_start_block(self):
        """Determines the starting block for event listening."""
        start_block_config = self.config['listener']['start_block']
        if isinstance(start_block_config, int):
            logging.info(f"Starting from configured block number: {start_block_config}")
            return start_block_config
        else: # 'latest'
            latest_block = self.source_connector.get_latest_block_number()
            if latest_block is not None:
                logging.info(f"Starting from the latest block: {latest_block}")
                return latest_block
            else:
                logging.error("Could not fetch the latest block. Exiting.")
                exit(1)

    def _get_current_gas_price_from_oracle(self):
        """(Simulation) Fetches gas price from an external API for informational purposes."""
        try:
            response = requests.get(self.config['gas_oracle_api'], timeout=10)
            response.raise_for_status() # Raises an HTTPError for bad responses
            data = response.json()
            return data.get('result', {}).get('ProposeGasPrice')
        except RequestException as e:
            logging.warning(f"Could not fetch gas price from oracle: {e}")
            return None

    def process_event(self, event):
        """
        Processes a single 'TokensLocked' event.
        This involves validation, state checking, and simulating the cross-chain action.
        """
        tx_hash = event['transactionHash'].hex()
        if self.state_db.is_processed(tx_hash):
            logging.debug(f"Skipping already processed transaction: {tx_hash}")
            return

        logging.info(f"Found new 'TokensLocked' event in transaction {tx_hash}")

        # --- 1. Data Extraction & Validation ---
        args = event.get('args', {})
        sender = args.get('from')
        amount = args.get('amount')
        target_chain_id = args.get('toChainId')

        if not all([sender, amount, target_chain_id]):
            logging.error(f"Malformed event in tx {tx_hash}. Missing arguments. Skipping.")
            return
        
        # --- 2. Business Logic Validation ---
        # Check if the target chain matches the one this listener is configured for.
        destination_chain_id = self.destination_connector.web3.eth.chain_id
        if target_chain_id != destination_chain_id:
            logging.warning(f"Event in tx {tx_hash} is for a different chain (ID: {target_chain_id}). Skipping.")
            return

        # --- 3. Simulate Destination Chain Action ---
        logging.info(f"Processing lock for {Web3.from_wei(amount, 'ether')} tokens from {sender}.")
        gas_price = self._get_current_gas_price_from_oracle()
        logging.info(f"(Oracle) Suggested gas price on Mainnet: {gas_price} Gwei")

        print('\n' + '-'*60)
        logging.info(
            f"SIMULATION: Triggering 'mint' on {self.destination_connector.name} bridge contract. "
            f"Recipient: {sender}, Amount: {amount}"
        )
        print('-'*60 + '\n')
        
        # --- 4. Update State ---
        self.state_db.mark_as_processed(tx_hash)

    def listen(self):
        """The main loop that polls for new blocks and processes events."""
        logging.info(f"Starting event listener for contract {self.source_connector.contract.address}...")

        while True:
            try:
                latest_block = self.source_connector.get_latest_block_number()
                if latest_block is None:
                    logging.warning("Could not get latest block. Retrying in {self.poll_interval}s...")
                    time.sleep(self.poll_interval)
                    continue

                if latest_block > self.last_processed_block:
                    from_block = self.last_processed_block + 1
                    to_block = latest_block
                    logging.info(f"Scanning blocks from {from_block} to {to_block}...")

                    event_filter = self.source_connector.contract.events.TokensLocked.create_filter(
                        fromBlock=from_block,
                        toBlock=to_block
                    )
                    events = event_filter.get_all_entries()

                    if events:
                        for event in events:
                            self.process_event(event)
                    else:
                        logging.info(f"No 'TokensLocked' events found in blocks {from_block}-{to_block}.")

                    self.last_processed_block = to_block
                else:
                    logging.debug("No new blocks to process.")

                time.sleep(self.poll_interval)

            except Exception as e:
                logging.error(f"An unexpected error occurred in the listener loop: {e}")
                logging.info(f"Restarting loop in {self.poll_interval * 2} seconds...")
                time.sleep(self.poll_interval * 2)


if __name__ == '__main__':
    # This is a guard to prevent execution when the script is imported.
    print("Cross-Chain Bridge Event Listener Simulator")
    print("===========================================")
    print("NOTE: This script uses placeholder values for RPC URLs and contract addresses.")
    print("It will not connect without valid configuration.")
    print("===========================================\n")

    # Basic configuration validation
    if 'YOUR_INFURA_PROJECT_ID' in CONFIG['source_chain']['rpc_url']:
        logging.error("Please replace 'YOUR_INFURA_PROJECT_ID' in the CONFIG section with your actual Infura Project ID.")
        exit(1)
    
    try:
        listener = CrossChainEventListener(CONFIG)
        listener.listen()
    except ConnectionError as e:
        logging.error(f"Initialization failed due to a connection error: {e}")
    except Exception as e:
        logging.error(f"A fatal error occurred during initialization: {e}")
