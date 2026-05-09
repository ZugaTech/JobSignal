import sys
import os
import asyncio
from pprint import pprint

# Ensure the root of the project is in the path
sys.path.append(os.getcwd())

# Manually load .env if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from backend.core.orchestrator import verify_job

async def test_full_workflow():
    print("--- TESTING FULL SYSTEM WORKFLOW ---")
    
    # Using a real-looking job URL and description
    job_url = "https://www.linkedin.com/jobs/view/123456789"
    job_text = """
    Senior AI Engineer at Gadian Corp.
    Responsibilities: Build trust systems using AMD ROCm.
    Requirements: 5 years experience, PhD preferred.
    Salary: $200k+
    """
    
    print(f"\nRunning verify_job for: {job_url}")
    try:
        # This calls the REAL orchestrator, which triggers Search and LLM
        report = await verify_job(
            job_url=job_url,
            job_description=job_text,
            request_id="test-workflow-001"
        )
        
        print("\n--- FINAL VERDICT ---")
        print(f"Verdict: {report['verdict']}")
        print(f"Confidence: {report['confidence']}")
        
        print("\n--- ACTIVE SIGNALS (From Search & LLM) ---")
        for s in report.get("signals", []):
            print(f"  [{s['id']}] {s['label']}: {s['strength']} (Source: {s.get('source', 'internal')})")
            
        print("\n--- PIPELINE STEPS TAKEN ---")
        for step in report.get("meta", {}).get("pipeline_steps", []):
            print(f"  - {step['label']}")
            
    except Exception as e:
        print(f"Workflow Test Failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_full_workflow())
