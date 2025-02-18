import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import OneHotEncoder
import json

class HospitalMLModel:
    def __init__(self):
        self.model = RandomForestClassifier(n_estimators=100, random_state=42)
        self.encoder = OneHotEncoder()
        self.is_trained = False

    def load_data(self, config_path='config.json'):
        with open(config_path, 'r') as file:
            config = json.load(file)
        # Simulate data preparation based on the configuration
        # This part should ideally interact with real patient data
        data = pd.DataFrame({
            'age': np.random.randint(0, 100, size=1000),
            'symptom_code': np.random.randint(1, 10, size=1000),
            'department': np.random.choice([dept['name'] for dept in config['departments_info']], 1000)
        })
        return data

    def prepare_features_labels(self, data):
        features = self.encoder.fit_transform(data[['age', 'symptom_code']])
        labels = data['department']
        return features, labels

    def train_model(self, X, y):
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        self.model.fit(X_train, y_train)
        self.is_trained = True
        print(f"Model trained with accuracy: {self.model.score(X_test, y_test)}")

    def predict_department(self, features):
        if not self.is_trained:
            raise Exception("Model has not been trained yet.")
        features = pd.DataFrame([features])
        features_transformed = self.encoder.transform(features)
        return self.model.predict(features_transformed)[0]

    def main(self, config_path='config.json'):
        data = self.load_data(config_path)
        X, y = self.prepare_features_labels(data)
        self.train_model(X, y)

if __name__ == "__main__":
    ml_model = HospitalMLModel()
    ml_model.main()
