import json
import os

def cleanup_json(file_path):
    if not os.path.exists(file_path):
        print(f"File {file_path} not found.")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")
            return

    if not isinstance(data, list):
        print("Data is not a list. Skipping cleanup.")
        return

    cleaned_count = 0
    for item in data:
        if "instructionsCN" in item and isinstance(item["instructionsCN"], list):
            # Check if any instruction contains the "MYMEMORY WARNING" phrase
            is_contaminated = any("MYMEMORY WARNING" in str(instr) for instr in item["instructionsCN"])
            if is_contaminated:
                del item["instructionsCN"]
                cleaned_count += 1

    if cleaned_count > 0:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Cleanup complete: Removed {cleaned_count} contaminated entries from {file_path}.")
    else:
        print("No contaminated entries found.")

if __name__ == "__main__":
    target_file = "free-exercise-db-main/dist/exercisesCN.json"
    cleanup_json(target_file)
