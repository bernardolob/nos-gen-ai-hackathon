import sys

def get_masked_text(attempt_num: int) -> str:
    """
    Simulates the masked text coming from another colleague/process.
    In the future, this function will call the actual anonymization module.
    """
    return f"""Relatório de Admissão - Centro Médico Lisboa (Tentativa {attempt_num})
Nome: * *
Data de Nascimento: */*/*
NIF: *
Histórico Médico: A paciente * * compareceu à consulta...
"""

def main():
    attempt = 1
    rejected_versions = []
    
    print("=== Starting Anonymization Review Process ===\n")
    
    while True:
        # Get the already masked text (simulated)
        masked_text = get_masked_text(attempt)
        
        print(f"--- CURRENT VERSION (Attempt {attempt}) ---")
        print(masked_text)
        print("----------------------------------------")
        
        # Ask the user
        resposta = input("Is the text good? (y/n): ").strip().lower()
        
        if resposta in ['y', 'yes']:
            print("\n✅ Excellent! The final text was approved and the process is complete.")
            # We could save the final file here, etc.
            break
        elif resposta in ['n', 'no']:
            print("\n❌ Version rejected.")
            print("Saving this version to the history for future comparison and restarting...\n")
            
            # Save the current version to be compared later
            rejected_versions.append({
                "attempt": attempt,
                "text": masked_text
            })
            
            attempt += 1
            #todo
            # In the final integration, we would call the LLM/Regex generation pipeline again here
            # or ask the user for clarification. For now, the loop restarts with a new attempt.
        else:
            print("\n⚠️ Invalid response. Please answer with 'y' (yes) or 'n' (no).\n")

    # Just as a proof of concept, we show that we saved the history
    if rejected_versions:
        print("\n--- REJECTED VERSIONS HISTORY ---")
        for item in rejected_versions:
            print(f"Attempt {item['attempt']} saved in memory (size: {len(item['text'])} characters).")
        print("---------------------------------------")
        #"It's still possible to implement the logic to compare these versions, if necessary."

if __name__ == "__main__":
    main()