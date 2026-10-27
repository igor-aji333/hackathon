import time
import json
from server import AirportRunwayManager

def run_evaluation():
    print("Initializing Data Service (Testing Cache & Download Lifecycle)...")
    start_time = time.time()
    
    # 1. Initialization Test
    # The new manager internally handles StorageManager, StorageConfig, and FAADataService
    manager = AirportRunwayManager()
    
    # Trigger initialization explicitly to measure startup/cache-load time
    manager._prepare_data()
    init_time = time.time() - start_time
    
    print(f"[SUCCESS] Initialization completed in {init_time:.2f}s")
    print(f"Dataset Rows: {len(manager.client.df)}, Cache Date: {manager.client.last_download}")

    # 2. Input Validation & Functional Tests
    test_cases = [
        {"id": "JFK", "desc": "Standard 3-letter FAA ID", "expect_found": True},
        {"id": "KJFK", "desc": "Standard 4-letter ICAO ID", "expect_found": True},
        {"id": "jfk", "desc": "Lowercase fallback", "expect_found": True},
        {"id": "XYZ9", "desc": "Invalid/Non-existent ID", "expect_found": False},
        {"id": "", "desc": "Empty string input", "expect_found": False},
    ]

    print("\nExecuting Tool Tool Queries...")
    for case in test_cases:
        q_start = time.time()
        try:
            result = manager.query(case["id"])
            q_time = (time.time() - q_start) * 1000
            
            if case["expect_found"]:
                assert result is not None, f"Failed: Expected to find {case['id']}"
                assert "runways" in result, f"Failed: Missing runway data for {case['id']}"
                print(f"[PASS] {case['desc']} ({case['id']}) - {q_time:.2f}ms - Found {len(result['runways'])} runways")
            else:
                assert result is None, f"Failed: Should not have found {case['id']}"
                print(f"[PASS] {case['desc']} ({case['id']}) - {q_time:.2f}ms - Gracefully handled")
                
        except Exception as e:
            print(f"[FAIL] {case['desc']} ({case['id']}) raised unexpected error: {e}")

if __name__ == "__main__":
    run_evaluation()
    
