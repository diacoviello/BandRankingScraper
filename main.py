import os
import requests
from bs4 import BeautifulSoup
import pandas as pd
from datetime import datetime, timedelta
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_email_with_gmail(csv_file_path):
    # Use environment variables for security
    receiver_email = "iacoviello.david@gmail.com"
    sender_email = os.getenv("EMAIL_USER")
    password = os.getenv("EMAIL_PASSWORD")

    # Set up the email content
    subject = "Weekly CSV Report"
    body = "Please find attached the latest CSV file."

    # Create the email
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain'))

    # Secure connection to Gmail's SMTP server
    try:
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()  # Start TLS encryption
        server.login(sender_email, password)

        # Send email
        with open(csv_file_path, 'rb') as attachment:
            msg.attach(MIMEText(attachment.read(), 'csv'))
            server.sendmail(sender_email, receiver_email, msg.as_string())
            print("Email sent successfully!")

    except Exception as e:
        print(f"Failed to send email: {e}")
    finally:
        server.quit()


# URL for the main events page
base_url = "https://usbands.org/events/"  # Ensure trailing slash
response = requests.get(base_url)
soup = BeautifulSoup(response.text, 'html.parser')

event_links = []
all_scores = []

# Define target states
target_states = ["NJ", "NY", "PA"]

# Get today's date
today = pd.to_datetime("today").normalize()
fourteen_days_ago = today - pd.DateOffset(days=14)
current_year = today.year  # Get the current year
start_of_week = today - timedelta(days=today.weekday())  # Start of week (Monday)
formatted_start_of_week = start_of_week.strftime('%B %d, %Y')

# Loop through all the event cards and collect event details and links
for card in soup.find_all('div', class_='card shadow mb-3 bg-white border-0 shadow'):
    row_div = card.find('div', class_='row')
    if not row_div:
        continue

    col_div = row_div.find('div', class_='col-md-9')
    if not col_div:
        continue

    event_div = col_div.find('div', class_='event past')
    if event_div is None:
        continue

    event_date_str = col_div.find('h5', class_='card-title').text.strip()
    event_host = event_div.find('a', class_='eventtitle').text.strip()

    event_state = event_div.find('div', class_='location').text.strip().split(",")[-1].strip()

    if event_state not in target_states:
        continue

    try:
        event_date = pd.to_datetime(f"{event_date_str}, {current_year}", format='%a, %b %d, %Y', errors='raise')
    except ValueError:
        continue

    if not (fourteen_days_ago <= event_date <= today):
        continue

    button_col_div = row_div.find('div', class_='col-md-3')
    if button_col_div:
        button = button_col_div.find('a', class_='btn btn-primary')
        if button:
            link = button['href']
            event_url = f"{base_url}{link}"
            event_links.append((event_url, event_host, event_date_str))

# Fetch the table for each event page
for event_url, event_host, event_date in event_links:
    print(f"Fetching scores from: {event_url}")  # Debugging line
    event_response = requests.get(event_url)

    if event_response.status_code != 200:
        print(f"Error: Unable to access {event_url}. Status code: {event_response.status_code}")
        continue

    event_soup = BeautifulSoup(event_response.text, 'html.parser')
    score_section = event_soup.select_one('main div.container-fluid table')

    if not score_section:
        print(f"Warning: No score table found for event: {event_host} ({event_url})")
        continue

    schedule_section = event_soup.find('h2', string='Schedule')  # Find the 'Schedule' heading
    performer_locations = {}

    if schedule_section:
        schedule_table = schedule_section.find_next('table')
        if schedule_table:
            for row in schedule_table.find_all('tr', class_='performingUnit'):
                unit_name_td = row.find('td', class_='unit')  # Get the entire <td> for the unit name and location
                unit_name = unit_name_td.find('a').text.strip()  # Extract unit name from <a>
                location = unit_name_td.find('div', class_='cityState').text.strip()  # Extract location from <div>

                performer_locations[unit_name.lower()] = location  # Store in the dictionary
                print(f"Added performer location: {unit_name} -> {location}")  # Debugging line

    current_division = None
    for row in score_section.find_all('tr'):
        if 'divisionName' in row.get('class', []):
            current_division = row.find('td').text.strip()
        else:
            rank_td = row.find('td', class_='rank')
            name_td = row.find('td', class_='name')
            score_td = row.find('td', class_='score')

            if rank_td and name_td and score_td:
                rank = rank_td.text.strip()
                name = name_td.text.strip()
                score = score_td.text.strip()

                # Normalize the name for comparison
                normalized_name = name.lower()

                # Find the performer location based on the normalized unit name
                performer_location = "Unknown Location"  # Default value

                # Check if the name matches a key in performer_locations
                if normalized_name in performer_locations:
                    performer_location = performer_locations[normalized_name]
                else:
                    # Try to find a match based on substring
                    for unit_name in performer_locations.keys():
                        if normalized_name in unit_name:
                            performer_location = performer_locations[unit_name]
                            print(f"Found substring match: {unit_name} -> {performer_location}")
                            break
                    else:
                        # If no match is found, modify the unit_name to create a location
                        if 'High School' in name:
                            performer_location = name.replace('High School', '').strip()  # Remove 'High School'
                            print(f"No direct match found. Using modified unit name as location: {performer_location}")

                # Ensure performer_location doesn't have duplicate town names
                # Using a set to track added towns
                unique_locations = set()
                location_parts = performer_location.split(', ')
                cleaned_location_parts = []

                for part in location_parts:
                    if part not in unique_locations:
                        unique_locations.add(part)
                        cleaned_location_parts.append(part)

                performer_location = ', '.join(cleaned_location_parts)

                # Parse the event date
                date_object = pd.to_datetime(f"{event_date_str}, {current_year}", format='%a, %b %d, %Y')

                # Format the date correctly
                formatted_date = date_object.strftime('%A, %B %d, %Y')

                # Append to the scores
                all_scores.append({
                    'Date': formatted_date,
                    'Division': current_division,
                    'Rank': int(rank),
                    'School': name,
                    'Score': float(score),
                    'Location': performer_location
                })

# Check if we collected any scores
if not all_scores:
    print("No scores were collected. Something went wrong with table extraction.")
else:
    print("Scores collected successfully.")

# Create a DataFrame from the scores
df = pd.DataFrame(all_scores)

# Convert the 'Date' column to datetime format
df['Date'] = pd.to_datetime(df['Date'], errors='coerce')  # Convert to datetime

# Remove the 'Date' column without affecting the index
df.drop(columns=['Date'], inplace=True)

# Sort DataFrame by Division, then Score in descending order
df_sorted = df.sort_values(by=['Division', 'Score'], ascending=[True, False])

# Assign ranks based on the sorted order
df_sorted['Rank'] = df_sorted.groupby('Division')['Score'].rank(method='min', ascending=False)

# Create a new DataFrame to store the final output with blank rows between divisions
output_df = pd.DataFrame()

# Iterate over each division and append data followed by a blank row
for division, group in df_sorted.groupby('Division'):
    output_df = pd.concat([output_df, group])  # Append the division's group
    output_df = pd.concat([output_df, pd.DataFrame(columns=group.columns)])  # Append a blank row

# Optionally, reset the index if you want a clean index in the output DataFrame
output_df.reset_index(drop=True, inplace=True)

# Now output_df contains the scores with blank rows between each division
print(output_df)


# Convert numeric ranking to ordinal string (1st, 2nd, 3rd, etc.)
def rank_to_ordinal(ranking):
    ranking = int(ranking)
    if 10 <= ranking % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(ranking % 10, 'th')
    return f"{ranking}{suffix}"


# Apply ranking to ordinal value
df_sorted['Rank'] = df_sorted['Rank'].apply(rank_to_ordinal)

# Ensure the Rank column is placed correctly
df_sorted.insert(1, 'Rank', df_sorted.pop('Rank'))


# Define the dynamic CSV file name
def generate_csv_file():
    csv = f"csv_files/all_scores_for_the_week_of_{formatted_start_of_week}.csv"

    if not df_sorted.empty:
        # Check if CSV exists and handle file operations
        try:
            existing_df = pd.read_csv(csv)
            if not existing_df.empty:
                first_date_in_csv = pd.to_datetime(existing_df['Date'].iloc[0])
                if first_date_in_csv == start_of_week:
                    # If the date is the same, overwrite the file
                    df_sorted.to_csv(csv, index=False)
                    print(f"Updated existing CSV: {csv}")
                else:
                    # Append new scores to the CSV
                    df_sorted.to_csv(csv, mode='a', header=False, index=False)
                    print(f"Appended new scores to CSV: {csv}")
            else:
                df_sorted.to_csv(csv, index=False)
                print(f"Created new CSV: {csv}")

        except FileNotFoundError:
            df_sorted.to_csv(csv, index=False)
            print(f"Created new CSV: {csv}")

        send_email_with_gmail(csv)  # Send the email after generating the CSV
    else:
        print("No scores available to save.")


# Call the function to generate the CSV file
generate_csv_file()
# send_email_with_gmail(csv_file)
