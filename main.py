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
        with open(csv_file, 'rb') as attachment:
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

# Example original date strings
original_date_strs = ["Sat, Sep 28", "Sun, Oct 05"]

# Initialize a list to hold the formatted dates
formatted_dates = []

# Assuming the current year is 2024
current_year = 2024

# Loop through each original date string
for original_date_str in original_date_strs:
    # Convert the string into a datetime object
    date_object = pd.to_datetime(f"{original_date_str}, {current_year}", format='%a, %b %d, %Y')

    # Format the date as "Saturday, September 28, 2024"
    formatted_date = date_object.strftime('%A, %B %d, %Y')

    # Store the formatted date
    formatted_dates.append(formatted_date)

# Display the formatted dates
for date in formatted_dates:
    print(date)  # Output: "Saturday, September 28, 2024" and "Sunday, October 05, 2024"

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
                unit_name = row.find('td', class_='unit').text.strip()
                location = row.find('div', class_='cityState').text.strip()
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
                    'Location': performer_location,
                    'Host': "".join('@ ' + event_host)
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


# Define the dynamic CSV file name
def generate_csv_file():
    csv = f"csv_files/all_scores_for_the_week_of_{formatted_start_of_week}.csv"
    # Sort by Date (ascending),  Division, Rank, and Host (all ascending)
    if not df.empty:
        df_sorted = df.sort_values(by=['Date', 'Division', 'Rank', 'Host'], ascending=[True, True, True, True])

        # Check if CSV exists and read the first row if so
        try:
            existing_df = pd.read_csv(csv)
            # Compare the date in the existing file with the current week's date
            if not existing_df.empty:
                first_date_in_csv = pd.to_datetime(existing_df['Date'].iloc[0])
                if first_date_in_csv == start_of_week:
                    # If the date is the same, overwrite the file
                    df_sorted.to_csv(csv, index=False)
                    print(f"Overwriting existing CSV file: {csv}")
                else:
                    # If the date is different, append the new data
                    combined_df = pd.concat([existing_df, df_sorted]).drop_duplicates()
                    combined_df.to_csv(csv, index=False)
                    print(f"Appending to CSV file: {csv}")
            else:
                # If existing CSV is empty, create it
                df_sorted.to_csv(csv, index=False)
                print(f"Creating new CSV file: {csv}")
        except FileNotFoundError:
            # If the CSV doesn't exist, create it
            df_sorted.to_csv(csv, index=False)
            print(f"Creating new CSV file: {csv}")
    return csv


# call to function to obtain correct path
csv_file = generate_csv_file()
send_email_with_gmail(csv_file)
