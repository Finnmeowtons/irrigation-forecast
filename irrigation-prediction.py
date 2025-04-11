import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
# train_test_split and mean_squared_error are optional if only forecasting
# from sklearn.model_selection import train_test_split
# from sklearn.metrics import mean_squared_error
from datetime import timedelta, datetime
import argparse # To handle command-line arguments
import warnings

# Suppress SettingWithCopyWarning, use with caution
warnings.filterwarnings('ignore', category=pd.errors.SettingWithCopyWarning)

def forecast_soil_moisture_threshold(csv_file_path, start_timestamp_iso, threshold=50.0, max_hours=72):
    """
    Loads data, trains a linear regression model, and forecasts from a specific
    start time until soil moisture drops below a given threshold.

    Args:
        csv_file_path (str): Path to the input CSV data file for training/initial state.
        start_timestamp_iso (str): ISO format string for the forecast start time.
        threshold (float): The soil moisture percentage threshold to predict.
        max_hours (int): The maximum number of hours to forecast ahead.

    Returns:
        str or None: ISO format timestamp string when the threshold is crossed,
                     or None if it's not crossed within max_hours.
    """
    # --- 1. Data Loading ---
    try:
        df = pd.read_csv(csv_file_path)
    except FileNotFoundError:
        print(f"Error: File not found at {csv_file_path}.")
        return None
    # print(f"Loaded data from {csv_file_path}")

    # --- 2. Preprocessing ---
    # print("Preprocessing data...")
    try:
        df = df.drop(columns=['id', 'device_id', 'nitrogen', 'phosphorus', 'potassium', 'soil_ph'])
    except KeyError as e:
        pass # Ignore if columns are already missing

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    interpolate_cols = ['temperature', 'humidity', 'soil_moisture_raw',
                        'soil_moisture_percentage', 'soil_temperature']
    missing_cols = [col for col in interpolate_cols if col not in df.columns]
    if missing_cols:
        print(f"Error: Missing required columns for interpolation: {missing_cols}")
        return None
    df[interpolate_cols] = df[interpolate_cols].interpolate(method='linear')

    # --- 3. Feature Engineering ---
    # print("Engineering features...")
    df['hour'] = df['timestamp'].dt.hour
    df['dayofweek'] = df['timestamp'].dt.weekday # Use weekday()
    df['moisture_lag1'] = df['soil_moisture_percentage'].shift(1)
    df['temp_lag1'] = df['temperature'].shift(1)
    df['humidity_lag1'] = df['humidity'].shift(1)
    df['soil_temp_lag1'] = df['soil_temperature'].shift(1)
    df_model = df.dropna().copy()

    if df_model.empty:
        print("Error: No data left after preprocessing for model training.")
        return None

    # --- 4. Model Training ---
    # print("Training linear regression model...")
    features = ['moisture_lag1', 'temp_lag1', 'humidity_lag1', 'soil_temp_lag1', 'hour', 'dayofweek']
    target = 'soil_moisture_percentage'
    
    missing_features = [feat for feat in features if feat not in df_model.columns]
    if missing_features:
         print(f"Error: Missing required feature columns for training: {missing_features}")
         return None

    X = df_model[features]
    y = df_model[target]
    model = LinearRegression()
    model.fit(X, y)

    # --- 5. Forecasting to Threshold ---
    last_known_data = df_model.iloc[-1].copy()
    try:
        forecast_start_time = datetime.fromisoformat(start_timestamp_iso)
    except ValueError:
        print(f"Error: Invalid start_timestamp_iso format. Please use YYYY-MM-DDTHH:MM:SS format.")
        return None
        
    current_features_dict = {
        'moisture_lag1': last_known_data['soil_moisture_percentage'],
        'temp_lag1': last_known_data['temperature'],
        'humidity_lag1': last_known_data['humidity'],
        'soil_temp_lag1': last_known_data['soil_temperature'],
        'hour': 0,
        'dayofweek': 0
    }
    features_order = features # List defining the order
    threshold_time_found = None

    for i in range(1, max_hours + 1):
        future_time = forecast_start_time + timedelta(hours=i)
        current_features_dict['hour'] = future_time.hour
        current_features_dict['dayofweek'] = future_time.weekday() # Use .weekday()

        # --- FIX: Create a DataFrame for prediction ---
        # Create a dictionary for the current row's data
        current_row_data = {feat: [current_features_dict[feat]] for feat in features_order}
        # Convert to DataFrame with the correct column order
        feature_df = pd.DataFrame(current_row_data, columns=features_order)
        # --- END FIX ---

        # Predict using the DataFrame
        predicted_moisture = model.predict(feature_df)[0]

        if predicted_moisture < threshold:
            threshold_time_found = future_time
            break

        # Update moisture lag for the next step
        current_features_dict['moisture_lag1'] = predicted_moisture

    # --- 6. Return Result ---
    if threshold_time_found:
        return threshold_time_found.isoformat()
    else:
        return None

# --- Main Execution Block ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Forecast soil moisture threshold time.")
    parser.add_argument("start_time", help="Forecast start timestamp in ISO format (e.g., 'YYYY-MM-DDTHH:MM:SS')")
    parser.add_argument("--datafile", default="dataset.csv", help="Path to the data CSV file")
    parser.add_argument("--threshold", type=float, default=50.0, help="Soil moisture threshold percentage")
    parser.add_argument("--maxhours", type=int, default=72, help="Maximum hours to forecast")

    args = parser.parse_args()

    predicted_iso_time = forecast_soil_moisture_threshold(
        csv_file_path=args.datafile,
        start_timestamp_iso=args.start_time,
        threshold=args.threshold,
        max_hours=args.maxhours
    )

    # Print the result for Node.js to capture
    if predicted_iso_time:
        print(predicted_iso_time)
    else:
        pass # Print nothing if not found