from chalice import Chalice, Rate
import boto3
import os
import requests
import logging 
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
import json

S3_BUCKET = os.environ.get('BUCKET_NAME','')

app = Chalice(app_name='life-sim-tracker')
app.log.setLevel(logging.INFO)

games = {
    "Sims4": "1222670",
    "Stardew": "413150",
    "Heartopia": "4025700"
}

s3 = boto3.client('s3')
db = boto3.resource('dynamodb')
table = db.Table('sim-table')

def update_plot():
    try:
        # 1. Fetch Data from DynamoDB (Same as before)
        start_time = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        all_items = []
        for name in games.keys():
            response = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('GameName').eq(name) & 
                                       boto3.dynamodb.conditions.Key('Timestamp').gt(start_time)
            )
            all_items.extend(response.get('Items', []))

        if not all_items: return

        # 2. Format Data for QuickChart (Chart.js format)
        # We need a list of unique timestamps for the X-axis labels
        all_items.sort(key=lambda x: x['Timestamp'])
        # Convert ISO strings to a format Chart.js loves (HH:mm)
        labels = sorted(list(set(item['Timestamp'] for item in all_items)))
        short_labels = [l[11:16] for l in labels] 

        datasets = []
        colors = {"Sims4": "#4bc0c0", "Stardew": "#ff6384", "Heartopia": "#9966ff"}

        for name in games.keys():
            game_map = {item['Timestamp']: int(item['Count']) for item in all_items if item['GameName'] == name}
            
            # Align data points to the master labels list
            data_points = [game_map.get(label, None) for label in labels]
            
            datasets.append({
                "label": name,
                "data": data_points,
                "fill": False,
                "borderColor": colors.get(name, "gray"),
                "borderWidth": 2,
                "pointRadius": 0,    # <--- THIS REMOVES THE POINTS
                "lineTension": 0.2   # Adds a slight smooth curve to the line
            })

        # 2. Build the Chart Config
        chart_config = {
            "type": "line",
            "data": {
                "labels": short_labels,
                "datasets": datasets
            },
            "options": {
                "title": {"display": True, "text": "Player Trends (Last 24h)", "fontSize": 18},
                "scales": {
                    "xAxes": [{
                        "ticks": {
                            "maxRotation": 0,   # Keeps labels horizontal
                            "autoSkip": True,   # Automatically hides labels if they crowd
                            "maxTicksLimit": 8  # Only shows ~8 time stamps total
                        }
                    }]
                }
            }
        }

        chart_str = json.dumps(chart_config)
        qc_url = f"https://quickchart.io/chart?c={quote(chart_str)}"

        app.log.info(f"Requesting chart from: {qc_url[:50]}...")
        response = requests.get(qc_url)
        
        try:
            if response.status_code == 200:
                # 5. Upload the resulting binary to S3
                s3.put_object(
                    Bucket=S3_BUCKET,
                    Key="latest_trends.png",
                    Body=response.content,
                    ContentType='image/png'
                )
                app.log.info("QuickChart uploaded to S3 successfully.")
        except Exception as e:
            app.log.error('Unable to retrieve plot form QuickChart: {e}')

    except Exception as e:
        app.log.error(f"QuickChart generation failed: {str(e)}")


@app.schedule(Rate(10, unit=Rate.MINUTES))
def periodic_ingest(event):
    current_time = datetime.now(timezone.utc).isoformat()
    
    for name, app_id in games.items():
        try:
            app.log.info(f"Attempting fetch for {name}...")
            url = f"https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid={app_id}"
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            
            player_count = response.json()['response'].get('player_count', 0)
            
            table.put_item(Item={
                'GameName': name,
                'Timestamp': current_time,
                'Count': player_count
            })
            app.log.info(f"Successfully recorded {name} player count at {current_time}")
        
            app.log.info("Ingestion complete. Updating graph")
            
        except Exception as e:
            app.log.error(f"Failed to ingest {name} player count: {str(e)}")

    try:
        update_plot()
        app.log.info('Plot update successful')
            
    except Exception as e:
        app.log.error(f"Periodic plot update failed: {str(e)}")

@app.route('/')
def index():
    return {
        "about": "Tracks Steam concurrent player counts from Sims 4, Stardew Valley, and Heartopia on Steam over time, sampled every 10 minutes.",
        "resources": ["current", "trend", "plot"],
    }

@app.route('/current', methods=['GET'])
def current():
    try:
        status_updates = []
        
        for name in games.keys():
            response = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('GameName').eq(name),
                ScanIndexForward=False,
                Limit=1
            )
            
            if response['Items']:
                data = response['Items'][0]
                player_count = data['Count']
                status_updates.append(f"{name} - {int(player_count):,}")
            else:
                status_updates.append(f"{name}: No data yet")

        result = " | ".join(status_updates)

        dt_object = datetime.fromisoformat(data['Timestamp'])
        readable_time = dt_object.strftime("%b %d, %I:%M %p")
        return {"response": f"Latest Player Counts as of {readable_time} UTC: {result}"}

    except Exception as e:
        app.log.error(f"Error in /current endpoint: {e}")
        return {"response": "Current player counts are unavailable."}

@app.route('/plot', methods=['GET'])
def get_plot_link():
    url = f"https://{S3_BUCKET}.s3.amazonaws.com/latest_trends.png?t={int(time.time())}"
    return {"response": url}


@app.route('/trend', methods=['GET'])
def trend():
    
    try:
        trend_reports = []
        
        for name in games.keys():
            response = table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('GameName').eq(name),
                ScanIndexForward=False, 
                Limit=7
            )
            
            items = response.get('Items', [])
            
            if len(items) < 7:
                trend_reports.append(f"{name} - Not enough items for hourly trend. Please check back later! ")
                continue
            
            latest_val = int(items[0]['Count'])
            hour_prior_val = int(items[6]['Count']) 
            
            diff = latest_val - hour_prior_val

            if diff < 0:
                stat = 'downward'

            elif diff > 0:
                stat = 'upward'
            
            else:
                stat = 'steady'

            trend_reports.append(f"{name}'s trend is {stat} ({diff:+})")

        return {"response": "Hourly Change:\n\n" + "\n".join(trend_reports)}

    except Exception as e:
        app.log.error(f"Trend Error: {e}")
        return {"response": "Error calculating hourly difference."}
