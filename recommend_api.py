import argparse
import pickle
import json

# Load models and encoders
rf_pipeline = pickle.load(open("fertilizer-model/rf_pipeline.pkl", "rb"))
fertname_dict = pickle.load(open("fertilizer-model/fertname_dict.pkl", "rb"))
soiltype_dict = pickle.load(open("fertilizer-model/soiltype_dict.pkl", "rb"))
croptype_dict = pickle.load(open("fertilizer-model/croptype_dict.pkl", "rb"))

def encode_input(data):
    soil_type_encoded = list(soiltype_dict.keys())[list(soiltype_dict.values()).index(data['soil_type'])]
    crop_type_encoded = list(croptype_dict.keys())[list(croptype_dict.values()).index(data['crop_type'])]
    return [[
        float(data['temperature']),
        float(data['humidity']),
        float(data['moisture']),
        soil_type_encoded,
        crop_type_encoded,
        float(data['N']),
        float(data['P']),
        float(data['K'])
    ]]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fertilizer recommendation input.")
    parser.add_argument("--temperature", required=True)
    parser.add_argument("--humidity", required=True)
    parser.add_argument("--moisture", required=True)
    parser.add_argument("--soil_type", required=True)
    parser.add_argument("--crop_type", required=True)
    parser.add_argument("--N", required=True)
    parser.add_argument("--P", required=True)
    parser.add_argument("--K", required=True)

    args = parser.parse_args()

    input_data = encode_input(vars(args))
    prediction = rf_pipeline.predict(input_data)[0]
    fertilizer_name = fertname_dict[prediction]
    print(json.dumps({"recommendation": fertilizer_name}))
