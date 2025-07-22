import pandas as pd

# File path
file_path = r"C:\Home Department\pending_case_stage_wise.xlsx"

# Load the Excel file
df = pd.read_excel(file_path)

# Drop duplicate rows
df_cleaned = df.drop_duplicates()

# Optionally, save the cleaned DataFrame back to the same file or to a new one
# Overwrite the original file:
# df_cleaned.to_excel(file_path, index=False)

# OR save to a new file
output_path = r"C:\Home Department\pending_case_stage_wise_cleaned.xlsx"
df_cleaned.to_excel(output_path, index=False)

print("Duplicate rows removed and cleaned file saved at:", output_path)
