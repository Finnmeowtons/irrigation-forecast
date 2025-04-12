const express = require('express');
const { spawn } = require('child_process');
const path = require('path');
const fs = require('fs');
const pool = require('./connection')

const app = express();
const PORT = 3003;

app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.get('/', (req, res) => {
    res.send('Express API server is running!');
});

app.get('/predict_irrigation_time', async (req, res) => {
    console.log('Received request for irrigation prediction...');

    try {
        // === 1. Query pool for latest timestamp ===
        const [rows] = await pool.query('SELECT MAX(timestamp) AS latest FROM data');

        if (!rows || rows.length === 0 || !rows[0].latest) {
            return res.status(400).json({ error: 'No timestamp found in database.' });
        }

        
        const latestTimestampISO = toLocalISOString(new Date(rows[0].latest));


        if (!latestTimestampISO) {
            return res.status(400).json({ error: 'No timestamp found in database.' });
        }

        console.log(`Using start timestamp: ${latestTimestampISO}`);

        // === 2. Export table to CSV ===
        const [exportRows] = await pool.query('SELECT * FROM data');

        if (exportRows.length === 0) {
            return res.status(400).json({ error: 'No data available for export.' });
        }

        const csvPath = path.join(__dirname, 'dataset.csv');
        const headers = Object.keys(exportRows[0]);
        const csvData = [headers.join(',')];

        exportRows.forEach(row => {
            // Convert timestamp to ISO string if it exists
            if (row.timestamp && row.timestamp instanceof Date) {
              row.timestamp = row.timestamp.toISOString();
            }
            csvData.push(headers.map(h => row[h]).join(','));
          });
          
        fs.writeFileSync(csvPath, csvData.join('\n'));
        console.log('Exported data to CSV:', csvPath);

        // === 3. Call Python Script in Conda Env ===
        const condaCommand = `conda run -n future_water_prediction python irrigation-prediction.py ${latestTimestampISO}`;
        const pythonProcess = spawn(condaCommand, {
            shell: true, // Needed for conda run to work
        });

        let predictionOutput = '';
        let errorOutput = '';

        pythonProcess.stdout.on('data', (data) => {
            predictionOutput += data.toString();
        });

        pythonProcess.stderr.on('data', (data) => {
            errorOutput += data.toString();
            console.error(`Python stderr: ${data}`);
        });

        pythonProcess.on('close', (code) => {
            console.log(`Python script exited with code ${code}`);

            if (code === 0) {
                const finalTimestamp = predictionOutput.trim();
                if (finalTimestamp) {
                    console.log('Python script successful. Predicted time:', finalTimestamp);
                    res.status(200).json({ irrigation_needed_at: finalTimestamp });
                } else {
                    console.log('Python script successful. Threshold not reached.');
                    res.status(200).json({ message: 'Threshold not predicted to be reached within forecast horizon.' });
                }
            } else {
                console.error('Python script failed.');
                res.status(500).json({ error: 'Prediction script failed.', details: errorOutput });
            }
        });

        pythonProcess.on('error', (err) => {
            console.error('Failed to start Python subprocess.', err);
            res.status(500).json({ error: 'Failed to start prediction process.' });
        });

    } catch (err) {
        console.error('Server error:', err);
        res.status(500).json({ error: 'Server error', details: err.message });
    }
});

app.get('/recommend-fertilizer', async (req, res) => {
    try {
        const [rows] = await pool.query(`
            SELECT * FROM data
            WHERE nitrogen IS NOT NULL
              AND phosphorus IS NOT NULL
              AND potassium IS NOT NULL
            ORDER BY timestamp DESC
            LIMIT 1
        `);

        if (!rows || rows.length === 0) {
            return res.status(404).json({ error: 'No valid NPK data found in the database.' });
        }

        const latestData = rows[0];
        let data = '';
        let error = '';

        const condaArgs = [
            'run', '-n', 'future_water_prediction', 'python', 'recommend_api.py',
            '--temperature', latestData.temperature.toString(),
            '--humidity', latestData.humidity.toString(),
            '--moisture', latestData.soil_moisture_percentage.toString(),
            '--soil_type', "Loamy",
            '--crop_type', "Maize",
            '--N', latestData.nitrogen.toString(),
            '--P', latestData.phosphorus.toString(),
            '--K', latestData.potassium.toString()
        ];

        console.log('Conda Args: ', condaArgs);
        const pythonProcess = spawn('conda', condaArgs, { shell: true });

        pythonProcess.stdout.on('data', (chunk) => {
            data += chunk.toString();
            console.log(data);
        });

        pythonProcess.stderr.on('data', (chunk) => {
            error += chunk.toString();
            console.error(`Python stderr: ${chunk}`);
        });

        pythonProcess.on('close', (code) => {
            console.log("Python process closed with code", code);
            if (code !== 0) {
                return res.status(500).json({ error: error || 'Prediction failed' });
            }
            try {
                const result = JSON.parse(data);
                res.json(result);
            } catch (err) {
                res.status(500).json({ error: 'Invalid response from Python script' });
            }
        });
    } catch (err) {
        console.error('Error during fertilizer recommendation:', err);
        res.status(500).json({ error: 'Server error', details: err.message });
    }
});



function toLocalISOString(date) {
    const tzOffset = date.getTimezoneOffset() * 60000;
    const localDate = new Date(date.getTime() - tzOffset);
    return localDate.toISOString().slice(0, 19);
  }

app.listen(PORT, () => {
    console.log(`Server listening on port ${PORT}`);
}); 
