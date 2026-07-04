from __future__ import annotations

import tempfile
import threading
import time
import uuid
from pathlib import Path

from .database import EventDatabase
from .types import BoundingBox, ConsensusDecision, CrossingEvent, Direction


def run_synthetic_counter_test(project_root: Path) -> int:
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        db_path = temp_path / "counter_test.db"
        print(f"Initializing synthetic test database at {db_path}...")
        db = EventDatabase(db_path)
        
        print("Resetting all counters and deleting existing table records...")
        db.reset_global_counts()
        
        num_threads = 10
        loops_per_thread = 100
        
        errors: list[str] = []
        
        def thread_worker(thread_idx: int) -> None:
            for i in range(loops_per_thread):
                # Unique person ID for this simulation step
                person_id = thread_idx * 10000 + i + 1
                
                # 1. Simulate entry
                bbox = BoundingBox(100.0, 100.0, 200.0, 200.0)
                passage_in = f"sim_in_{uuid.uuid4().hex}"
                event_in = CrossingEvent(
                    camera_id="camera_1",
                    local_track_id=i,
                    direction=Direction.IN,
                    timestamp=time.time(),
                    zone="entry",
                    bbox=bbox,
                    confidence=0.99,
                    global_person_id=person_id,
                    passage_id=passage_in
                )
                decision_in = ConsensusDecision(
                    event=event_in,
                    counted=True,
                    duplicate_of=None,
                    uncertain=False,
                    reason="synthetic_test_in"
                )
                
                try:
                    db.record_decision(decision_in, "synthetic_test_model")
                except Exception as e:
                    errors.append(f"Thread-{thread_idx} loop-{i} Entry error: {e}")
                    
                # 2. Simulate exit
                passage_out = f"sim_out_{uuid.uuid4().hex}"
                event_out = CrossingEvent(
                    camera_id="camera_2",
                    local_track_id=i,
                    direction=Direction.OUT,
                    timestamp=time.time(),
                    zone="exit",
                    bbox=bbox,
                    confidence=0.99,
                    global_person_id=person_id,
                    passage_id=passage_out
                )
                decision_out = ConsensusDecision(
                    event=event_out,
                    counted=True,
                    duplicate_of=None,
                    uncertain=False,
                    reason="synthetic_test_out"
                )
                
                try:
                    db.record_decision(decision_out, "synthetic_test_model")
                except Exception as e:
                    errors.append(f"Thread-{thread_idx} loop-{i} Exit error: {e}")
                    
        threads = []
        print(f"Launching {num_threads} parallel threads...")
        for idx in range(num_threads):
            t = threading.Thread(target=thread_worker, args=(idx,))
            threads.append(t)
            t.start()
            
        for t in threads:
            t.join()
            
        print("All threads finished. Fetching counts from database...")
        counts = db.restore_counts()
        db.close()
        
        # Print structured results
        print("\n" + "="*50)
        print("SYNTHETIC GLOBAL COUNTER TEST RESULTS")
        print("="*50)
        print(f"Threads launched: {num_threads}")
        print(f"Loops per thread: {loops_per_thread}")
        print(f"Expected Entered: {num_threads * loops_per_thread}")
        print(f"Expected Exited:  {num_threads * loops_per_thread}")
        print(f"Expected Inside:  0")
        print("-"*50)
        print(f"Actual Entered:   {counts['entered']}")
        print(f"Actual Exited:    {counts['exited']}")
        print(f"Actual Inside:    {counts['inside']}")
        print(f"Errors captured:  {len(errors)}")
        for err in errors[:5]:
            print(f"  ERROR: {err}")
        if len(errors) > 5:
            print(f"  ... and {len(errors) - 5} more errors")
        print("="*50)
        
        # Validation checks
        success = True
        if counts['entered'] != 1000:
            print("FAIL: Entered count is not 1000")
            success = False
        if counts['exited'] != 1000:
            print("FAIL: Exited count is not 1000")
            success = False
        if counts['inside'] != 0:
            print("FAIL: Inside count is not 0")
            success = False
        if errors:
            print("FAIL: Thread errors occurred during test")
            success = False
            
        print(f"test_database={db_path}")
        print("production_database_untouched=true")
        
        if success:
            print("RESULT: SUCCESS - Global counter is thread-safe and correct!")
            return 0
        else:
            print("RESULT: FAILURE - Race condition or error detected")
            return 1
