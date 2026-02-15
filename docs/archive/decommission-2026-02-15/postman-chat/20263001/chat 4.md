refactoring.md

metadata

Visualize the response as a chart



Command executed

The workspace doesn't have a postman folder yet. Since this is a local workspace and the active tab is an unsaved request (not part of a collection), I need to save the test script directly to the request. Let me send the request first to understand the response structure, then add the visualizer.



Send request errored out.

The request has an issue. Let me create the visualizer code that handles both response shapes (array of objects or object with data array). Since this is an unsaved request in a local workspace, I'll provide the exact code to add to the Tests tab.

Here's the complete visualizer code for the Tests tab:

```
// Postman Visualizer - Line Chart with 
    Chart.js
var template = `
<div style="padding: 20px; font-family: 
    Arial, sans-serif;">
    <div id="error-message" style="color: 
         #e74c3c; padding: 10px; display: 
        none;"></div>
    <canvas id="myChart" height="100"></
        canvas>
</div>
<script src="https://cdnjs.cloudflare.com/
    ajax/libs/Chart.js/2.5.0/Chart.min.js"></
    script>
<script>
    pm.getData(function (err, value) {
        var errorDiv = document.
            getElementById('error-message');
        var chartData = value.chartData;
        
        if (!chartData || !chartData.
            labels || chartData.labels.
            length === 0) {
            errorDiv.style.display = 'block';
            errorDiv.innerHTML = '<strong>No 
                data available.</strong> 
                Expected JSON response with 
                array of objects containing 
                "date", "a", and "b" fields, 
                or an object with a "data" 
                array field.';
            return;
        }
        
        var ctx = document.getElementById
            ('myChart');
        var myChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: chartData.labels,
                datasets: [
                    {
                        label: 'Series A',
                        data: chartData.
                            seriesA,
                        borderColor: ' rgba
                            (54, 162, 235, 1)
                            ',
                        backgroundColor: 
                            ' rgba(54, 162, 
                            235, 0.2)',
                        fill: false,
                        tension: 0.1
                    },
                    {
                        label: 'Series B',
                        data: chartData.
                            seriesB,
                        borderColor: ' rgba
                            (255, 99, 132, 1)
                            ',
                        backgroundColor: 
                            ' rgba(255, 99, 
                            132, 0.2)',
                        fill: false,
                        tension: 0.1
                    }
                ]
            },
            options: {
                responsive: true,
                legend: { display: true },
                title: {
                    display: true,
                    text: 'Line Chart - 
                        Series A vs Series B'
                },
                scales: {
                    xAxes: [{
                        display: true,
                        scaleLabel: {
                            display: true,
                            labelString: 
                                'Date'
                        }
                    }],
                    yAxes: [{
                        display: true,
                        scaleLabel: {
                            display: true,
                            labelString: 
                                'Value'
                        }
                    }]
                }
            }
        });
    });
</script>
`;

function constructVisualizerPayload() {
    var chartData = {
        labels: [],
        seriesA: [],
        seriesB: []
    };

    try {
        var response = pm.response.json();
        var dataArray = null;

        // Check if response is an array 
            directly
        if (Array.isArray(response)) {
            dataArray = response;
        }
        // Check if response is an object 
            with a 'data' array field
        else if (response && typeof response 
            === 'object' && Array.isArray
            (response.data)) {
            dataArray = response.data;
        }

        // Extract data if we have a valid 
            array
        if (dataArray && dataArray.length > 
            0) {
            dataArray.forEach(function 
                (item) {
                if (item && item.date !== 
                    undefined) {
                    chartData.labels.push
                        (item.date);
                    chartData.seriesA.push
                        (item.a !== 
                        undefined ? item.a : 
                        null);
                    chartData.seriesB.push
                        (item.b !== 
                        undefined ? item.b : 
                        null);
                }
            });
        }
    } catch (e) {
        console.log('Error parsing response 
            for visualizer: ' + e.message);
    }

    return { chartData: chartData };
}

pm.visualizer.set(template, 
    constructVisualizerPayload());
```

**To add this to your request:**

1. Click on the **Tests** tab in the active request (ID: `ef382522-076a-4611-b8dc-1c392302953d`)
2. Paste the code above into the Tests editor
3. Send the request to see the visualization in the **Visualize** tab of the response

**What this visualizer does:**

- Renders a line chart using Chart.js with two datasets: "Series A" and "Series B"
- Handles two response shapes:
  - **Array of objects**: `[{date: "...", a: 1, b: 2}, ...]`
  - **Object with data array**: `{data: [{date: "...", a: 1, b: 2}, ...]}`
- Shows a friendly error message if the data is missing or in an unexpected format
- Includes defensive checks for undefined values



Job completed successfully

The request has an issue. Let me create the visualizer code that handles both response shapes (array of objects or object with data array). Since this is an unsaved request in a local workspace, I'll provide the exact code to add to the Tests tab.

Here's the complete visualizer code for the Tests tab:

```
// Postman Visualizer - Line Chart with 
    Chart.js
var template = `
<div style="padding: 20px; font-family: 
    Arial, sans-serif;">
    <div id="error-message" style="color: 
         #e74c3c; padding: 10px; display: 
        none;"></div>
    <canvas id="myChart" height="100"></
        canvas>
</div>
<script src="https://cdnjs.cloudflare.com/
    ajax/libs/Chart.js/2.5.0/Chart.min.js"></
    script>
<script>
    pm.getData(function (err, value) {
        var errorDiv = document.
            getElementById('error-message');
        var chartData = value.chartData;
        
        if (!chartData || !chartData.
            labels || chartData.labels.
            length === 0) {
            errorDiv.style.display = 'block';
            errorDiv.innerHTML = '<strong>No 
                data available.</strong> 
                Expected JSON response with 
                array of objects containing 
                "date", "a", and "b" fields, 
                or an object with a "data" 
                array field.';
            return;
        }
        
        var ctx = document.getElementById
            ('myChart');
        var myChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: chartData.labels,
                datasets: [
                    {
                        label: 'Series A',
                        data: chartData.
                            seriesA,
                        borderColor: ' rgba
                            (54, 162, 235, 1)
                            ',
                        backgroundColor: 
                            ' rgba(54, 162, 
                            235, 0.2)',
                        fill: false,
                        tension: 0.1
                    },
                    {
                        label: 'Series B',
                        data: chartData.
                            seriesB,
                        borderColor: ' rgba
                            (255, 99, 132, 1)
                            ',
                        backgroundColor: 
                            ' rgba(255, 99, 
                            132, 0.2)',
                        fill: false,
                        tension: 0.1
                    }
                ]
            },
            options: {
                responsive: true,
                legend: { display: true },
                title: {
                    display: true,
                    text: 'Line Chart - 
                        Series A vs Series B'
                },
                scales: {
                    xAxes: [{
                        display: true,
                        scaleLabel: {
                            display: true,
                            labelString: 
                                'Date'
                        }
                    }],
                    yAxes: [{
                        display: true,
                        scaleLabel: {
                            display: true,
                            labelString: 
                                'Value'
                        }
                    }]
                }
            }
        });
    });
</script>
`;

function constructVisualizerPayload() {
    var chartData = {
        labels: [],
        seriesA: [],
        seriesB: []
    };

    try {
        var response = pm.response.json();
        var dataArray = null;

        // Check if response is an array 
            directly
        if (Array.isArray(response)) {
            dataArray = response;
        }
        // Check if response is an object 
            with a 'data' array field
        else if (response && typeof response 
            === 'object' && Array.isArray
            (response.data)) {
            dataArray = response.data;
        }

        // Extract data if we have a valid 
            array
        if (dataArray && dataArray.length > 
            0) {
            dataArray.forEach(function 
                (item) {
                if (item && item.date !== 
                    undefined) {
                    chartData.labels.push
                        (item.date);
                    chartData.seriesA.push
                        (item.a !== 
                        undefined ? item.a : 
                        null);
                    chartData.seriesB.push
                        (item.b !== 
                        undefined ? item.b : 
                        null);
                }
            });
        }
    } catch (e) {
        console.log('Error parsing response 
            for visualizer: ' + e.message);
    }

    return { chartData: chartData };
}

pm.visualizer.set(template, 
    constructVisualizerPayload());
```

**To add this to your request:**

1. Click on the **Tests** tab in the active request (ID: `ef382522-076a-4611-b8dc-1c392302953d`)
2. Paste the code above into the Tests editor
3. Send the request to see the visualization in the **Visualize** tab of the response

**What this visualizer does:**

- Renders a line chart using Chart.js with two datasets: "Series A" and "Series B"
- Handles two response shapes:
  - **Array of objects**: `[{date: "...", a: 1, b: 2}, ...]`
  - **Object with data array**: `{data: [{date: "...", a: 1, b: 2}, ...]}`
- Shows a friendly error message if the data is missing or in an unexpected format
- Includes defensive checks for undefined values

Here’s a visualizer you can drop directly into the Tests tab of your current request to see a chart of the response.

This version:

- Uses Chart.js for a line chart
- Expects either:
  - An array of objects: `[{ date: "...", a: 1, b: 2 }, ...]`, or
  - An object with `data` array: `{ data: [{ date: "...", a: 1, b: 2 }, ...] }`
- Shows a message if the shape doesn’t match

Paste this into the **Tests** tab:

```
// Visualize the response as a line chart 
    using Chart.js

var template = `
<div style="padding: 16px; font-family: 
    Arial, sans-serif;">
  <div id="error-message" 
    style="color:#e74c3c; 
    margin-bottom:12px; display:none;"></div>
  <canvas id="myChart" height="100"></canvas>
</div>

<script src="https://cdnjs.cloudflare.com/
    ajax/libs/Chart.js/2.5.0/Chart.min.js"></
    script>

<script>
  pm.getData(function (err, value) {
    var errorDiv = document.getElementById
        ('error-message');
    var chartData = value && value.
        chartData ? value.chartData : null;

    if (!chartData || !chartData.labels || 
        chartData.labels.length === 0) {
      errorDiv.style.display = 'block';
      errorDiv.innerHTML =
        '<strong>No plottable data found.</
            strong><br>' +
        'Expected JSON like:<br>' +
        '[{ "date": "2024-01-01", "a": 1, 
            "b": 2 }, ...]<br>' +
        'or<br>' +
        '{ "data": [{ "date": "2024-01-01", 
            "a": 1, "b": 2 }, ...] }';
      return;
    }

    var ctx = document.getElementById
        ('myChart');

    new Chart(ctx, {
      type: 'line',
      data: {
        labels: chartData.labels,
        datasets: [
          {
            label: 'Series A',
            data: chartData.seriesA,
            borderColor: ' rgba(54, 162, 
                235, 1)',
            backgroundColor: ' rgba(54, 162, 
                235, 0.1)',
            fill: false,
            lineTension: 0.1,
            pointRadius: 3
          },
          {
            label: 'Series B',
            data: chartData.seriesB,
            borderColor: ' rgba(255, 99, 
                132, 1)',
            backgroundColor: ' rgba(255, 99, 
                132, 0.1)',
            fill: false,
            lineTension: 0.1,
            pointRadius: 3
          }
        ]
      },
      options: {
        responsive: true,
        legend: { display: true },
        title: {
          display: true,
          text: 'Series A vs Series B'
        },
        scales: {
          xAxes: [{
            display: true,
            scaleLabel: {
              display: true,
              labelString: 'Date'
            }
          }],
          yAxes: [{
            display: true,
            scaleLabel: {
              display: true,
              labelString: 'Value'
            }
          }]
        }
      }
    });
  });
</script>
`;

function constructVisualizerPayload() {
    var chartData = {
        labels: [],
        seriesA: [],
        seriesB: []
    };

    try {
        var response = pm.response.json();
        var dataArray = null;

        // Case 1: response is directly an 
        if (Array.isArray(response)) {
            dataArray = response;
        }
        // Case 2: response is an object 
            with a `data` array
        else if (response && typeof response 
            === 'object' && Array.isArray
            (response.data)) {
            dataArray = response.data;
        }

        if (dataArray && dataArray.length > 
            dataArray.forEach(function 
                if (!item || item.date === 
                    undefined) {
                    return;
                }
                chartData.labels.push(item.
                chartData.seriesA.push(item.
                    a !== undefined ? item.a 
                chartData.seriesB.push(item.
                    b !== undefined ? item.b 
            });
        }
    } catch (e) {
        console.log('Visualizer parsing 
            error:', e.message);
    }
            array
            0) {
                (item) {
                    date);
                    : null);
                    : null);

    return { chartData: chartData };
}

pm.visualizer.set(template, 
    constructVisualizerPayload());
```

How to use:

1. Open your request’s **Tests** tab.
2. Replace any existing content (or append) with the code above.
3. Send the request.
4. In the response area, switch to the **Visualize** tab to see the chart.

If your response doesn’t use `date`, `a`, and `b`, tell me the actual JSON shape (or paste a sample), and I’ll adjust this to map the correct fields.

refactoring.md

metadata

{ "data": { "tracks": [ { "__typename": "Track", "uri": "spotify:track:7jXQeX92kFbE5bh4XFpLxo", "name": "Pompadour - Catz n' Dogz Remix", "albumOfTrack": { "uri": "spotify:album:1R7RsN6kHsfi3Z5ZvB5z9f", "name": "Berlin Underground Selection (Finest Electronic Music)", "coverArt": { "sources": [ { "height": 300, "width": 300, "url": "https://i.scdn.co/image/ab67616d00001e025d6fc18d891a909969a67a01" }, { "height": 64, "width": 64, "url": "https://i.scdn.co/image/ab67616d000048515d6fc18d891a909969a67a01" }, { "height": 640, "width": 640, "url": "https://i.scdn.co/image/ab67616d0000b2735d6fc18d891a909969a67a01" } ] } }, "artists": { "items": [ { "uri": "spotify:artist:4kHMPa8ypDqdgC5bKkyQeM", "profile": { "name": "Chelonis R. Jones" } }, { "uri": "spotify:artist:5tYqFEuFELxnJZgGmmsfSh", "profile": { "name": "Catz 'n Dogz" } } ] }, "duration": { "totalMilliseconds": 499298 }, "playability": { "playable": true }, "relinkingInformation": { "linkedTrack": { "__typename": "Track", "uri": "spotify:track:7DiCxtecyRvX8eYQtRtTwa" } } } ] } } this album

You’re getting back a Spotify-style payload; the earlier visualizer was expecting `date`, `a`, and `b`, so let’s change it to visualize *this* data instead.

From your sample, the interesting numeric fields we can chart per track are:

- Track duration: `duration.totalMilliseconds`
- Album cover sizes: `albumOfTrack.coverArt.sources[].height` or `.width`

Below is a Visualizer script that:

- Plots **track duration (seconds)** per track as a bar chart
- Uses the **track name** as the label
- Works with responses shaped like your example:
  - `response.data.tracks` is an array of tracks

Paste this into the **Tests** tab of the same request:

```
// Visualize Spotify tracks as a bar chart 
    of duration

var template = `
<div style="padding: 16px; font-family: 
    Arial, sans-serif;">
  <h3 style="margin-top:0;">Track durations</
    h3>
  <div id="error-message" 
    style="color:#e74c3c; 
    margin-bottom:12px; display:none;"></div>
  <canvas id="durationChart" height="100"></
    canvas>
</div>

<script src="https://cdnjs.cloudflare.com/
    ajax/libs/Chart.js/2.5.0/Chart.min.js"></
    script>

<script>
  pm.getData(function (err, value) {
    var errorDiv = document.getElementById
        ('error-message');
    var chartData = value && value.
        chartData ? value.chartData : null;

    if (!chartData || !chartData.labels || 
        chartData.labels.length === 0) {
      errorDiv.style.display = 'block';
      errorDiv.innerHTML =
        '<strong>No track data found.</
            strong><br>' +
        'Expected response like: { "data": { 
            "tracks": [{ "name": "...", 
            "duration": { 
            "totalMilliseconds": 
            123456 } }, ...] } }';
      return;
    }

    var ctx = document.getElementById
        ('durationChart');

    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: chartData.labels,
        datasets: [
          {
            label: 'Duration (seconds)',
            data: chartData.durationSeconds,
            backgroundColor: ' rgba(54, 162, 
                235, 0.5)',
            borderColor: ' rgba(54, 162, 
                235, 1)',
            borderWidth: 1
          }
        ]
      },
      options: {
        responsive: true,
        legend: { display: true },
        title: {
          display: true,
          text: 'Track durations'
        },
        scales: {
          xAxes: [{
            ticks: {
              autoSkip: false
            }
          }],
          yAxes: [{
            scaleLabel: {
              display: true,
              labelString: 'Seconds'
            },
            ticks: {
              beginAtZero: true
            }
          }]
        },
        tooltips: {
          callbacks: {
            label: function(tooltipItem, 
                data) {
              var label = data.labels
                [tooltipItem.index] || '';
              var seconds = data.datasets[0].
                data[tooltipItem.index];
              return label + ': ' + seconds 
                + 's';
            }
          }
        }
      }
    });
  });
</script>
`;

function constructVisualizerPayload() {
    var chartData = {
        labels: [],
        durationSeconds: []
    };

    try {
        var response = pm.response.json();

        // Expecting: { data: { tracks: 
            [ ... ] } }
        var tracks =
            response &&
                response.data &&
                Array.isArray(response.data.
                ? response.data.tracks
                : [];

        tracks.forEach(function (track) {
            if (!track) {
                return;
            }

            var name = track.name || '(no 
            var ms =
                track.duration &&
                    typeof track.duration.
                        totalMilliseconds 
                    ? track.duration.
                    : null;

            if (ms !== null) {
                chartData.labels.push(name);
                chartData.durationSeconds.
                    push(Math.round(ms / 
            }
        });
    } catch (e) {
        console.log('Visualizer parsing 
            error:', e.message);
    }

                    tracks)
                name)';
                        === 'number'
                        totalMilliseconds
                    1000));
    return { chartData: chartData };
}

pm.visualizer.set(template, 
    constructVisualizerPayload());
```

How to see it:

1. Open the request you’re using to get this Spotify response.
2. Go to the **Tests** tab and paste the script above.
3. Send the request.
4. In the response pane, switch to **Visualize** to see the bar chart of track durations.

If you’d rather chart something else (e.g., number of artists per track, or cover art sizes), tell me what you want on the X and Y axes and I’ll tweak the script.

POST

https://api-partner.spotify.com/pathfinder/v2/query

postman request POST 'https://api-partner.spotify.com/pathfinder/v2/query' \ --header 'Content-Type: application/json;charset=UTF-8' \ --header 'Authorization: Bearer BQAeYWlUb7QnLRqfqVhKlQa6HqSyATiZad-VfTRXB5o_1XQN6AypWKjEtIOvjUlsOAmV40kgXhvAUbzM8GlGjkWAsbf4_WdYkvVjG9jAOQWCI7KIsTG4EX4tGlsmvXvCfl0Slzmca1pGU-kbIe6KAcOEq85FHDloroQDKVLbJJm5Cn9Xms7-5rLl50CScqjeY2CL4eQ0v3ziNLer6LR8Ez-Zl4Pq-k-YHMKbiI3opGVcbPgNDjry8Ny3DenVJ2OwqnyMxqisOuvQL3UlOLiIExqgECm4wJiSRWfKWYJVSa5GYNfpwiKEjPsRpCZDCC1lfkfcD7QGbgH-DQfM_4g6tbG7mC0K_089pOpMUQD8yjpxQZ9Z7jzTeC7x' \ --header 'Accept: application/json' \ --header 'Sec-Fetch-Site: same-site' \ --header 'Accept-Language: en' \ --header 'Sec-Fetch-Mode: cors' \ --header 'Origin: https://open.spotify.com' \ --header 'Referer: https://open.spotify.com/' \ --header 'User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.2 Safari/605.1.15' \ --header 'Sec-Fetch-Dest: empty' \ --header 'spotify-app-version: 896000000' \ --header 'app-platform: WebPlayer' \ --header 'client-token: AADD5dT2HVjPyawMfVQGieluLTfB0j24zNTHyPVF0PSrPZqG8Uepk7nzJncuN4PSBMYGzLxDsqcnLsa7Ar/cQhphLoQ+FWI+zC8A+Y9dPQiFrT76pjgzgEvqg8k3AzUlw7aNAtLd5y/f5CWyHZVNOnnWZZTt4Q6aIi7QOSAR3GqsvsuKX406wm9VLRuZpH/UeWqI9HTxZqXCVh6XI/qFBBURvhQvWrRN7LO0YkSb/enK8iJlRN3ZqQgrznOJUdsKyufQlQkWml/8LcRQBl7yrlLCzvoxjMu41qtJ6djpmp7lYKkAhDxr7YfO6NCOw0DC9QyYikM/d/ijbcrFIMm34l81NiG1jll6' \ --header 'host: api-partner.spotify.com' \ --header 'Cookie: sp_t=3f0cd36f-8b75-43e9-b621-cbe2740700c6' \ --body '{"variables":{"uri":"spotify:album:1R7RsN6kHsfi3Z5ZvB5z9f","locale":"","offset":0,"limit":50},"operationName":"getAlbum","extensions":{"pers ion":1,"sha256Hash":"b9bfabef66ed756e5e13f68a942deb60bd4125ec1f1be8cc42769dc0259b4b10"}}}' /Users/georgeskhawam/Projects/tagslut/album.json

You already have this request open in Postman (the unsaved POST to `https://api-partner.spotify.com/pathfinder/v2/query` with the album URI in the body). Let’s wire everything together so that:

- The request hits Spotify’s album endpoint (as in your curl),
- The response is visualized as a chart (e.g., track durations),
- And you can reuse the JSON you saved at `/Users/georgeskhawam/Projects/tagslut/album.json` as a sample.

You don’t need a collection; you can work right in the current request tab.

------

### 1. Make sure the request is set up in Postman

You’ve effectively copied a curl command; in Postman it should look like:

- Method: `POST`
- URL: `https://api-partner.spotify.com/pathfinder/v2/query`
- Headers (you already have these in your active tab):
  - `Content-Type: application/json;charset=UTF-8`
  - `Authorization: Bearer <your-long-token>`
  - `Accept: application/json`
  - `Origin: https://open.spotify.com`
  - `Referer: https://open.spotify.com/`
  - `User-Agent: Mozilla/...`
  - `spotify-app-version: 896000000`
  - `app-platform: WebPlayer`
  - `client-token: <long client token>`
  - `host: api-partner.spotify.com`
  - `Cookie: sp_t=3f0cd36f-8b75-43e9-b621-cbe2740700c6` (optional, but you mirrored browser traffic)

Body (raw → JSON):

```
{
    "variables": {
        "uri": 
            "spotify:album:1R7RsN6kHsfi3Z5ZvB
            5z9f",
        "locale": "",
        "offset": 0,
        "limit": 50
    },
    "operationName": "getAlbum",
    "extensions": {
        "persistedQuery": {
            "version": 1,
            "sha256Hash": 
                "b9bfabef66ed756e5e13f68a942d
                eb60bd4125ec1f1be8cc42769dc02
                59b4b10"
        }
    }
}
```

Make sure the JSON isn’t truncated (your curl line was cut at `pers...`; it must be valid JSON exactly like above).

------

### 2. Add a chart visualizer for this album response

Your actual album response (from the selected request) is shaped like:

```
{
    "data": {
        "albumUnion": {
            "tracksV2": {
                "items": [
                    {
                        "track": {
                            "name": "...",
                            "duration": {
                                "totalMillise
                                    conds": 
                                    449177
                            },
                            "playability": {
                                "playable": 
                                    true
                            },
                            "playcount": 
                                "155800",
                            "uri": 
                                "spotify:trac
                                k:...",
              ...
                        },
                        "uid": "..."
                    },
          ...
                ]
            }
        }
    }
}
```

So we’ll:

- Plot **track duration** (in seconds) per track,
- Use **track names** on the X-axis,
- Optionally expose **playcount** in tooltips.

Paste this into the **Tests** tab of the POST request:

```
// Visualize Spotify album tracks as a bar 
    chart of durations

var template = `
<div style="padding: 16px; font-family: 
    Arial, sans-serif;">
  <h3 style="margin-top:0;">Album tracks – 
    durations</h3>
  <div id="error-message" 
    style="color:#e74c3c; 
    margin-bottom:12px; display:none;"></div>
  <canvas id="tracksChart" height="110"></
    canvas>
</div>

<script src="https://cdnjs.cloudflare.com/
    ajax/libs/Chart.js/2.5.0/Chart.min.js"></
    script>

<script>
  pm.getData(function (err, value) {
    var errorDiv = document.getElementById
        ('error-message');
    var chartData = value && value.
        chartData ? value.chartData : null;

    if (!chartData || !chartData.labels || 
        chartData.labels.length === 0) {
      errorDiv.style.display = 'block';
      errorDiv.innerHTML =
        '<strong>No track data found.</
            strong><br>' +
        'Expected shape similar to Spotify 
            album GraphQL: ' +
        'data.albumUnion.tracksV2.items[].
            track.duration.
            totalMilliseconds';
      return;
    }

    var ctx = document.getElementById
        ('tracksChart');

    new Chart(ctx, {
      type: 'bar',
      data: {
        labels: chartData.labels,
        datasets: [
          {
            label: 'Duration (seconds)',
            data: chartData.durationSeconds,
            backgroundColor: ' rgba(54, 162, 
                235, 0.5)',
            borderColor: ' rgba(54, 162, 
                235, 1)',
            borderWidth: 1
          }
        ]
      },
      options: {
        responsive: true,
        legend: { display: true },
        title: {
          display: true,
          text: 'Track durations for album'
        },
        scales: {
          xAxes: [{
            ticks: {
              autoSkip: false,
              maxRotation: 60,
              minRotation: 30
            }
          }],
          yAxes: [{
            scaleLabel: {
              display: true,
              labelString: 'Seconds'
            },
            ticks: {
              beginAtZero: true
            }
          }]
        },
        tooltips: {
          callbacks: {
            label: function(tooltipItem, 
                data) {
              var name = data.labels
                [tooltipItem.index] || '';
              var seconds = data.datasets[0].
                data[tooltipItem.index];
              var extra = '';
              if (value && value.
                chartData && value.chartData.
                playcounts) {
                var pc = value.chartData.
                    playcounts[tooltipItem.
                    index];
                if (pc !== undefined && pc 
                    !== null) {
                  extra = ' – plays: ' + pc;
                }
              }
              return name + ': ' + seconds + 
                's' + extra;
            }
          }
        }
      }
    });
  });
</script>
`;

function constructVisualizerPayload() {
    var chartData = {
        labels: [],
        durationSeconds: [],
        playcounts: []  // optional, for 
    };

    try {
        var response = pm.response.json();

        // Navigate: data.albumUnion.
            tracksV2.items[]
        var items =
            response &&
                response.data &&
                response.data.albumUnion &&
                response.data.albumUnion.
                Array.isArray(response.data.
                    albumUnion.tracksV2.
                ? response.data.albumUnion.
                    tracksV2.items
                : [];

        items.forEach(function (item) {
            if (!item || !item.track) return;

            var track = item.track;
            var name = track.name || '(no 

            var ms = (
                track.duration &&
                typeof track.duration.
                    totalMilliseconds === 
            )
                ? track.duration.
                : null;

            // Spotify returns playcount as 
            var playcount = track.playcount 
                !== undefined ? track.

            if (ms !== null) {
                chartData.labels.push(name);
                chartData.durationSeconds.
                    push(Math.round(ms / 
                chartData.playcounts.push
            }
        });
    } catch (e) {
            tooltips
                    tracksV2 &&
                    items)
                name)';
                    'number'
                    totalMilliseconds
                string
                playcount : null;
                    1000));
                    (playcount);
        // Safe logging in Postman console
        console.log('Visualizer parsing 
            error:', e.message);
    }

    return { chartData: chartData };
}

pm.visualizer.set(template, 
    constructVisualizerPayload());
```

------

### 3. Use your saved `album.json` for testing (optional)

Since you have `/Users/georgeskhawam/Projects/tagslut/album.json`:

- Open that file and confirm it matches a real response body.
- In Postman, instead of calling Spotify every time, you can:
  - Use the **Mock Server** feature with that body, or
  - Temporarily paste the file’s JSON as a manual response in a [saved example](https://desktop.postman.com/?desktopVersion=11.82.1&userId=49297136&teamId=10867715&region=us#) for a saved request, then send the request and inspect the Visualize tab.

Given you’re in a local workspace with no collections yet, the simplest path is:

1. Keep sending the real request with your browser-derived token until it expires.
2. Once you get a 200 with album data, just rely on that live response to drive the chart.

------

### 4. Next possible refinements

If you tell me what you most want to see:

- timeline of playcount per track (bar),
- playable vs non-playable counts (pie),
- durations per disc if multi-disc albums (stacked bar),

I can give you a second chart (same visualizer, multiple `<canvas>` elements) tailored exactly for that.

POST

https://api-partner.spotify.com/pathfinder/v2/query

no no this is different. i want to tag the album, which i already have but mistagged by error

Got it—you’re not trying to chart this; you’re trying to *fix the tags* for an album file you already have locally (e.g., MP3/FLAC), and you just used the Spotify request to get the correct metadata.

Postman can help you fetch and structure the right data from Spotify, but it can’t directly edit audio file tags. You’ll do the tagging with another tool, but we can make Postman give you a clean, copy‑pasteable “tag sheet” from the API response so you don’t mistype anything again.

Given your album JSON, here’s a good workflow:

1. Use your existing POST request to Spotify to get the album metadata.
2. Add a Visualizer or Tests script that extracts:
   - Album title
   - Album artist
   - Track titles
   - Track numbers
   - Track artists (joined)
   - Duration (optional, for verification)
3. Use that output to retag the album files in your tag editor.

Below is a simple **table visualizer** that extracts exactly the tag info you’d want.

### 1. Add this to the Tests tab (for your `getAlbum` POST)

In the same POST request to `https://api-partner.spotify.com/pathfinder/v2/query`, open **Tests** and paste:

```
// Build a simple tag sheet for this Spotify 
    album

var template = `
<div style="font-family: Arial, sans-serif; 
    padding: 12px;">
  <h3 style="margin-top: 0;">Album tag 
    sheet</h3>
  <p><strong>Album:</strong> {{album.name}}</
    p>
  <p><strong>Album Artist:</strong> {{album.
    artist}}</p>
  <p><strong>Album URI:</strong> {{album.
    uri}}</p>

  <table border="1" cellspacing="0" 
    cellpadding="4" style="border-collapse: 
    collapse; margin-top: 12px; font-size: 
    12px;">
    <thead style="background:#f0f0f0;">
      <tr>
        <th>#</th>
        <th>Title</th>
        <th>Track Artists</th>
        <th>Duration (mm:ss)</th>
        <th>Spotify URI</th>
        <th>Playcount</th>
      </tr>
    </thead>
    <tbody>
      {{#each tracks}}
      <tr>
        <td>{{trackNumber}}</td>
        <td>{{name}}</td>
        <td>{{artists}}</td>
        <td>{{duration}}</td>
        <td>{{uri}}</td>
        <td>{{playcount}}</td>
      </tr>
      {{/each}}
    </tbody>
  </table>
</div>
`;

function msToMinSec(ms) {
    if (typeof ms !== 'number') return '';
    var totalSeconds = Math.round(ms / 1000);
    var minutes = Math.floor(totalSeconds / 
        60);
    var seconds = totalSeconds % 60;
    return minutes + ':' + (seconds < 10 ? 
        '0' + seconds : seconds);
}

function constructVisualizerPayload() {
    var album = {
        name: '',
        artist: '',
        uri: ''
    };
    var tracks = [];

    try {
        var response = pm.response.json();

        // Path: data.albumUnion
        var albumNode = response &&
            response.data &&
            response.data.albumUnion
            ? response.data.albumUnion
            : null;

        if (albumNode) {
            album.name = albumNode.name || 
            album.uri = albumNode.uri || '';

            // Album artist(s)
            if (albumNode.artists &&
                Array.isArray(albumNode.
                    artists.items) &&
                albumNode.artists.items.
                    length > 0) {
                album.artist = albumNode.
                    artists.items
                    .map(function (a) {
                        return a.profile && 
                            a.profile.name ? 
                    })
                    .filter(function (n) { 
                    .join(', ');
            }
        }

        // Tracks: data.albumUnion.tracksV2.
            items[]
        var items =
            albumNode &&
                albumNode.tracksV2 &&
                Array.isArray(albumNode.
                ? albumNode.tracksV2.items
                : [];

        items.forEach(function (item) {
            if (!item || !item.track) return;

            var t = item.track;

            // Track artists
            var artists = '';
            if (t.artists &&
                Array.isArray(t.artists.
                artists = t.artists.items
                    .map(function (a) {
                        return (a.profile && 
                            a.profile.
                    })
                    .filter(function (n) { 
                    .join(', ');
            }

            var ms = t.duration &&
                typeof t.duration.
                    totalMilliseconds === 
                    'number'
                ? t.duration.
                : null;

            tracks.push({
                trackNumber: t.
                name: t.name || '',
                artists: artists,
                duration: msToMinSec(ms),
                uri: t.uri || '',
                playcount: t.playcount || ''
            });
        });
    } catch (e) {
                '';
                            a.profile.name : 
                            '';
                        return n; })
                    tracksV2.items)
                    items)) {
                            name) ? a.
                            profile.name : 
                            '';
                        return n; })
                    totalMilliseconds
                    trackNumber || '',
        // If parsing fails, you'll still 
            see an empty template
    }

    return {
        album: album,
        tracks: tracks
    };
}

pm.visualizer.set(template, 
    constructVisualizerPayload());
```

### 2. How to use this to retag your album

1. Send the `getAlbum` POST request again.
2. In the response pane, click the **Visualize** tab.
3. You’ll see a table with:
   - Album name + Album Artist (good for `ALBUM` and `ALBUMARTIST` tags).
   - Per‑track: track number, title, artist(s), duration, URI, playcount.
4. Open your tagging tool (Mp3Tag, Kid3, etc.) and:
   - Correct each file’s `TITLE`, `ARTIST`, `TRACK`, `ALBUM`, `ALBUMARTIST`, etc., using the Visualizer table as source of truth.

If you tell me:

- What exactly is “mistagged” (album name, track order, artists, etc.), and
- Which fields you care about most,

I can adjust the Visualizer to highlight mismatches (e.g., compare your current file names vs. Spotify track titles, or export a CSV‑style string you can paste).

POST

https://api-partner.spotify.com/pathfinder/v2/query

thats all? get all the tags

You can get essentially *all* the useful tag data for the album from this one Spotify response and surface it in Postman. The Visualizer can expose far more than just basic title/artist.

From your `getAlbum` response, you can map to typical audio tags like:

- Album-level:
  - `ALBUM` – album name
  - `ALBUMARTIST` – album artist / Various Artists
  - `DATE` / `YEAR` – album date
  - `LABEL` – label
  - `ALBUMTYPE` – album type (COMPILATION, ALBUM, etc.)
  - `ALBUMURI` – Spotify album URI (custom tag)
  - `COVER URL` – album art URL(s)
- Track-level:
  - `TITLE` – track name
  - `ARTIST` – primary artists
  - `TRACKNUMBER`
  - `DISCNUMBER`
  - `DURATION` – duration (mm:ss or seconds)
  - `TRACKURI` – Spotify track URI
  - `ISPLAYABLE` – playable flag
  - `PLAYCOUNT` – playcount
  - Optionally, relinked URI, explicit flag, etc.

Below is an expanded Visualizer that pulls *all of these* fields from `data.albumUnion` and `tracksV2.items`. You’ll get two sections:

1. Album tags (key/value list)
2. Track tags (full table per track)

Paste this into the **Tests** tab of your `getAlbum` POST:

```
// Comprehensive tag sheet for this Spotify 
    album

var template = `
<div style="font-family: Arial, sans-serif; 
    padding: 12px; max-width: 1200px;">
  <h3 style="margin-top: 0;">Album tag sheet 
    (Spotify)</h3>

  <h4>Album tags</h4>
  <table border="1" cellspacing="0" 
    cellpadding="4" style="border-collapse: 
    collapse; margin-bottom: 16px; 
    font-size: 12px; min-width: 400px;">
    <tbody>
      <tr><td><strong>ALBUM</strong></td><td>
        {{album.name}}</td></tr>
      <tr><td><strong>ALBUMARTIST</strong></
        td><td>{{album.albumArtist}}</td></
        tr>
      <tr><td><strong>ALBUMTYPE</strong></
        td><td>{{album.type}}</td></tr>
      <tr><td><strong>DATE</strong></td><td>
        {{album.date}}</td></tr>
      <tr><td><strong>YEAR</strong></td><td>
        {{album.year}}</td></tr>
      <tr><td><strong>LABEL</strong></td><td>
        {{album.label}}</td></tr>
      <tr><td><strong>ALBUMURI</strong></
        td><td>{{album.uri}}</td></tr>
      <tr><td><strong>COVER URL (300)</
        strong></td><td>{{album.cover300}}</
        td></tr>
      <tr><td><strong>COVER URL (640)</
        strong></td><td>{{album.cover640}}</
        td></tr>
    </tbody>
  </table>

  <h4>Track tags</h4>
  <table border="1" cellspacing="0" 
    cellpadding="4" style="border-collapse: 
    collapse; font-size: 12px; width: 100%;">
    <thead style="background:#f0f0f0;">
      <tr>
        <th>DISCNUMBER</th>
        <th>TRACKNUMBER</th>
        <th>TITLE</th>
        <th>ARTIST</th>
        <th>DURATION (mm:ss)</th>
        <th>TRACKURI</th>
        <th>ISPLAYABLE</th>
        <th>PLAYCOUNT</th>
      </tr>
    </thead>
    <tbody>
      {{#each tracks}}
      <tr>
        <td>{{discNumber}}</td>
        <td>{{trackNumber}}</td>
        <td>{{title}}</td>
        <td>{{artist}}</td>
        <td>{{duration}}</td>
        <td>{{uri}}</td>
        <td>{{isPlayable}}</td>
        <td>{{playcount}}</td>
      </tr>
      {{/each}}
    </tbody>
  </table>
</div>
`;

function msToMinSec(ms) {
    if (typeof ms !== 'number') return '';
    var totalSeconds = Math.round(ms / 1000);
    var minutes = Math.floor(totalSeconds / 
        60);
    var seconds = totalSeconds % 60;
    return minutes + ':' + (seconds < 10 ? 
        '0' + seconds : seconds);
}

function safeGetAlbumDate(albumNode) {
    if (!albumNode || !albumNode.date) 
        return { full: '', year: '' };
    var iso = albumNode.date.isoString || '';
    if (!iso) return { full: '', year: '' };
    // isoString like "2009-09-18T00:00:00Z"
    var year = iso.slice(0, 4);
    return { full: iso, year: year };
}

function constructVisualizerPayload() {
    var album = {
        name: '',
        albumArtist: '',
        uri: '',
        type: '',
        date: '',
        year: '',
        label: '',
        cover300: '',
        cover640: ''
    };

    var tracks = [];

    try {
        var response = pm.response.json();

        // Album-level: data.albumUnion
        var albumNode = response &&
            response.data &&
            response.data.albumUnion
            ? response.data.albumUnion
            : null;

        if (albumNode) {
            album.name = albumNode.name || 
            album.uri = albumNode.uri || '';
            album.type = albumNode.type || 
                ''; // e.g. COMPILATION, 
            album.label = albumNode.label || 

            // Album date/year
            var dateInfo = safeGetAlbumDate
                (albumNode);
            album.date = dateInfo.full;
            album.year = dateInfo.year;

            // Album artist(s): data.
                albumUnion.artists.items[].
            if (albumNode.artists &&
                Array.isArray(albumNode.
                    artists.items) &&
                albumNode.artists.items.
                    length > 0) {
                album.albumArtist = 
                    albumNode.artists.items
                    .map(function (a) {
                        return a.profile && 
                            a.profile.name ? 
                    })
                    .filter(function (n) { 
                    .join(', ');
            }

            // Cover art URLs: data.
                albumUnion.coverArt.sources[]
            if (albumNode.coverArt &&
                Array.isArray(albumNode.
                    coverArt.sources)) {
                albumNode.coverArt.sources.
                    forEach(function (src) {
                    if (!src || !src.url) 
                    if (src.height === 
                        300 || src.width === 
                        album.cover300 = src.
                    }
                    if (src.height === 
                        640 || src.width === 
                        album.cover640 = src.
                    }
                });
            }
        }

        // Tracks: data.albumUnion.tracksV2.
            items[]
        var items =
            albumNode &&
                albumNode.tracksV2 &&
                Array.isArray(albumNode.
                ? albumNode.tracksV2.items
                : [];

        items.forEach(function (item) {
            if (!item || !item.track) return;

            var t = item.track;

            // Track artists: t.artists.items
                [].profile.name
            var artist = '';
            if (t.artists && Array.isArray(t.
                artists.items)) {
                artist = t.artists.items
                    .map(function (a) {
                        return a.profile && 
                            a.profile.name ? 
                    })
                    .filter(function (n) { 
                    .join(', ');
            }

            var ms = (
                t.duration &&
                typeof t.duration.
                    totalMilliseconds === 
            ) ? t.duration.totalMilliseconds 
                : null;

            var discNumber = t.discNumber 
                !== undefined ? t.discNumber 
            var trackNumber = t.trackNumber 
                !== undefined ? t.

            tracks.push({
                discNumber: discNumber,
                trackNumber: trackNumber,
                title: t.name || '',
                artist: artist,
                duration: msToMinSec(ms),
                uri: t.uri || '',
                isPlayable: t.playability && 
                    typeof t.playability.
                '';
                ALBUM
                '';
                profile.name
                            a.profile.name : 
                            '';
                        return n; })
                        return;
                        300) {
                            url;
                        640) {
                            url;
                    tracksV2.items)
                            a.profile.name : 
                            '';
                        return n; })
                    'number'
                : '';
                trackNumber : '';
                    playable === 'boolean'
                    ? String(t.playability.
                        playable)
                    : '',
                playcount: t.playcount || ''
            });
        });
    } catch (e) {
        // if parsing fails, we just send 
            what we have (likely empty)
    }

    return {
        album: album,
        tracks: tracks
    };
}

pm.visualizer.set(template, 
    constructVisualizerPayload());
```

How to use this:

1. In your `POST https://api-partner.spotify.com/pathfinder/v2/query` request, open **Tests**.
2. Paste the script above.
3. Send the request.
4. In the response pane, open the **Visualize** tab.
5. You now have:
   - A compact **Album tags** table to fill `ALBUM`, `ALBUMARTIST`, `YEAR`, `LABEL`, etc.
   - A full **Track tags** table for each file: DISCNUMBER, TRACKNUMBER, TITLE, ARTIST, DURATION, URI, PLAYABLE, PLAYCOUNT.

From there, you just copy these values into your tagging app to fix the mistagged album.

If you want additional fields (e.g., ISRC if available, explicit flag, genres if you’re pulling those from another part of the response), tell me which tags you use (e.g. `TXXX/SPOTIFY_TRACK_URI`, `COMPILATION`, etc.), and I’ll extend this sheet accordingly.

POST

https://api-partner.spotify.com/pathfinder/v2/query

i want EERYTHINGT

Understood: you want to squeeze *everything useful for tagging* out of Spotify’s album response and see it in one place.

We can’t literally dump every single nested field into a readable visual, but we can:

1. Extract a very rich, tag-oriented view (album + tracks),
2. Also show a **raw JSON dump** section so nothing is hidden from you.

Below is a **maximal tag sheet** for your `getAlbum` response shape (`data.albumUnion` with `tracksV2.items`). It includes:

- Album-level:
  - ALBUM, ALBUMARTIST(s), TYPE, DATE, YEAR, LABEL
  - URI, share URL, share ID
  - Disc counts, track counts
  - Cover URLs of multiple sizes + extracted cover colors (hex) if present
- Per-track:
  - DISCNUMBER, TRACKNUMBER, TITLE
  - ARTIST(S) (joined), ALBUM (of track), ALBUM URI
  - DURATION (mm:ss + ms)
  - TRACKURI, relinked URI (if any)
  - PLAYABLE flag + reason
  - PLAYCOUNT
  - EXPLICIT (content rating)
  - Saved flag, UID
  - Any available video association count (for reference)

And at the bottom:

- A `<pre>` with a **pretty-printed JSON snippet** for the album node (so you can inspect everything else that isn’t explicitly mapped yet).

------

Paste this into the **Tests** tab of your `getAlbum` request:

```
// MAXIMAL-ish Spotify Album Tag Sheet from 
    getAlbum response

var template = `
<div style="font-family: Arial, sans-serif; 
    padding: 12px; max-width: 1400px;">
  <h3 style="margin-top: 0;">Spotify Album 
    Tag Sheet (Rich)</h3>

  <h4>Album tags</h4>
  <table border="1" cellspacing="0" 
    cellpadding="4" style="border-collapse: 
    collapse; margin-bottom: 16px; 
    font-size: 12px; min-width: 500px;">
    <tbody>
      <tr><td><strong>ALBUM</strong></td><td>
        {{album.name}}</td></tr>
      <tr><td><strong>ALBUMARTIST</strong></
        td><td>{{album.albumArtist}}</td></
        tr>
      <tr><td><strong>ALBUMTYPE</strong></
        td><td>{{album.type}}</td></tr>
      <tr><td><strong>DATE</strong></td><td>
        {{album.date}}</td></tr>
      <tr><td><strong>YEAR</strong></td><td>
        {{album.year}}</td></tr>
      <tr><td><strong>LABEL</strong></td><td>
        {{album.label}}</td></tr>
      <tr><td><strong>DISCS</strong></td><td>
        {{album.discCount}}</td></tr>
      <tr><td><strong>TOTAL TRACKS</strong></
        td><td>{{album.totalTrackCount}}</
        td></tr>
      <tr><td><strong>ALBUMURI</strong></
        td><td>{{album.uri}}</td></tr>
      <tr><td><strong>SHARE URL</strong></
        td><td>{{album.shareUrl}}</td></tr>
      <tr><td><strong>SHARE ID</strong></
        td><td>{{album.shareId}}</td></tr>
      <tr><td><strong>COVER URL (64)</
        strong></td><td>{{album.cover64}}</
        td></tr>
      <tr><td><strong>COVER URL (300)</
        strong></td><td>{{album.cover300}}</
        td></tr>
      <tr><td><strong>COVER URL (640)</
        strong></td><td>{{album.cover640}}</
        td></tr>
      <tr><td><strong>COVER COLOR (DARK)</
        strong></td><td>{{album.colorDark}}</
        td></tr>
      <tr><td><strong>COVER COLOR (LIGHT)</
        strong></td><td>{{album.colorLight}}
        </td></tr>
      <tr><td><strong>COVER COLOR (RAW)</
        strong></td><td>{{album.colorRaw}}</
        td></tr>
    </tbody>
  </table>

  <h4>Track tags (per track)</h4>
  <table border="1" cellspacing="0" 
    cellpadding="4" style="border-collapse: 
    collapse; font-size: 11px; width: 100%; 
    table-layout: fixed;">
    <thead style="background:#f0f0f0;">
      <tr>
        <th style="width:4%;">DISC</th>
        <th style="width:4%;">TRACK</th>
        <th style="width:18%;">TITLE</th>
        <th style="width:18%;">ARTIST(S)</th>
        <th style="width:12%;">ALBUM OF 
            TRACK</th>
        <th style="width:8%;">DURATION 
            (mm:ss / ms)</th>
        <th style="width:14%;">TRACKURI</th>
        <th style="width:10%;">RELINKED URI</
            th>
        <th style="width:5%;">PLAYABLE</th>
        <th style="width:7%;">PLAY REASON</
            th>
        <th style="width:8%;">PLAYCOUNT</th>
        <th style="width:4%;">EXPL</th>
      </tr>
    </thead>
    <tbody>
      {{#each tracks}}
      <tr>
        <td>{{discNumber}}</td>
        <td>{{trackNumber}}</td>
        <td>{{title}}</td>
        <td>{{artists}}</td>
        <td>{{albumName}}</td>
        <td>{{duration}} / {{durationMs}}</
            td>
        <td style="word-wrap:break-word;">
            {{uri}}</td>
        <td style="word-wrap:break-word;">
            {{relinkedUri}}</td>
        <td>{{isPlayable}}</td>
        <td>{{playReason}}</td>
        <td>{{playcount}}</td>
        <td>{{explicit}}</td>
      </tr>
      {{/each}}
    </tbody>
  </table>

  <h4 style="margin-top:20px;">Raw album 
    JSON (pretty-printed subset)</h4>
  <p style="font-size:11px; color:#555;">
    This is a pretty-printed JSON of the 
        <code>data.albumUnion</code> node so 
        you can inspect any other fields
    that are not explicitly shown above. For 
        absolutely everything, copy the 
        response body from the raw tab.
  </p>
  <pre style="font-size:11px; 
    max-height:400px; overflow:auto; 
    background:#f8f8f8; padding:8px; 
    border:1px solid  #ddd;">
{{rawAlbumJson}}
  </pre>
</div>
`;

function msToMinSec(ms) {
    if (typeof ms !== 'number') return '';
    var totalSeconds = Math.round(ms / 1000);
    var minutes = Math.floor(totalSeconds / 
        60);
    var seconds = totalSeconds % 60;
    return minutes + ':' + (seconds < 10 ? 
        '0' + seconds : seconds);
}

function safeGetAlbumDate(albumNode) {
    if (!albumNode || !albumNode.date) 
        return { full: '', year: '' };
    var iso = albumNode.date.isoString || '';
    if (!iso) return { full: '', year: '' };
    var year = iso.slice(0, 4);
    return { full: iso, year: year };
}

function getCoverSources(albumNode) {
    var result = {
        cover64: '',
        cover300: '',
        cover640: '',
        colorDark: '',
        colorLight: '',
        colorRaw: ''
    };

    if (!albumNode || !albumNode.coverArt) 
        return result;

    if (Array.isArray(albumNode.coverArt.
        sources)) {
        albumNode.coverArt.sources.forEach
            (function (src) {
            if (!src || !src.url) return;
            if (src.height === 64 || src.
                width === 64) {
                result.cover64 = src.url;
            }
            if (src.height === 300 || src.
                width === 300) {
                result.cover300 = src.url;
            }
            if (src.height === 640 || src.
                width === 640) {
                result.cover640 = src.url;
            }
        });
    }

    // Extracted color info if present
    if (albumNode.coverArt.extractedColors &&
        albumNode.coverArt.extractedColors.
            colorDark &&
        albumNode.coverArt.extractedColors.
            colorDark.hex) {
        result.colorDark = albumNode.
            coverArt.extractedColors.
    }
    if (albumNode.coverArt.extractedColors &&
        albumNode.coverArt.extractedColors.
            colorLight &&
        albumNode.coverArt.extractedColors.
            colorLight.hex) {
        result.colorLight = albumNode.
            coverArt.extractedColors.
    }
    if (albumNode.coverArt.extractedColors &&
        albumNode.coverArt.extractedColors.
            colorRaw &&
        albumNode.coverArt.extractedColors.
            colorRaw.hex) {
        result.colorRaw = albumNode.coverArt.
            extractedColors.colorRaw.hex;
    }

    return result;
}

function getAlbumArtistString(albumNode) {
    if (!albumNode || !albumNode.artists || 
        !Array.isArray(albumNode.artists.
        items)) {
        return '';
    }
    return albumNode.artists.items
        .map(function (a) {
            return a.profile && a.profile.
                name ? a.profile.name : '';
        })
        .filter(function (n) { return n; })
        .join(', ');
}

function getDiscAndTrackCounts(albumNode) {
    var discCount = '';
    var trackCount = '';

    if (albumNode && albumNode.discs && 
        Array.isArray(albumNode.discs.
        discCount = albumNode.discs.items.
        // try to sum track counts if 
        var sum = 0;
        albumNode.discs.items.forEach
            (function (disc) {
            if (disc.tracks && typeof disc.
                tracks.totalCount === 
                sum += disc.tracks.
            }
        });
        if (sum > 0) {
            trackCount = sum;
        }
    }

    // fallback to tracksV2.totalCount
    if (!trackCount && albumNode && 
        albumNode.tracksV2 && typeof 
        albumNode.tracksV2.totalCount === 
        trackCount = albumNode.tracksV2.
            totalCount;
    }

    return { discCount: discCount, 
        trackCount: trackCount };
}

function constructVisualizerPayload() {
    var album = {
        name: '',
        albumArtist: '',
        uri: '',
        type: '',
        date: '',
        year: '',
        label: '',
        discCount: '',
        totalTrackCount: '',
        shareUrl: '',
        shareId: '',
        cover64: '',
        cover300: '',
        cover640: '',
        colorDark: '',
        colorLight: '',
        colorRaw: ''
    };

    var tracks = [];
    var rawAlbumJson = '';

    try {
        var response = pm.response.json();

        // Album-level: data.albumUnion
        var albumNode = response &&
            response.data &&
            response.data.albumUnion
            ? response.data.albumUnion
            : null;

        if (albumNode) {
            // Pretty-printed subset (album 
                node) for the raw view
            rawAlbumJson = JSON.stringify
                (albumNode, null, 2);

            album.name = albumNode.name || 
            album.uri = albumNode.uri || '';
            album.type = albumNode.type || 
                ''; // e.g. COMPILATION, 
            album.label = albumNode.label || 

            var dateInfo = safeGetAlbumDate
                (albumNode);
            album.date = dateInfo.full;
            album.year = dateInfo.year;

            album.albumArtist = 
                getAlbumArtistString

            var counts = 
                getDiscAndTrackCounts
            album.discCount = counts.
            album.totalTrackCount = counts.
                trackCount;

            // sharingInfo if present
            if (albumNode.sharingInfo) {
                album.shareUrl = albumNode.
                    sharingInfo.shareUrl || 
                album.shareId = albumNode.
                    sharingInfo.shareId || 
            }

            // cover art and colors
            var covers = getCoverSources
                (albumNode);
            album.cover64 = covers.cover64;
            album.cover300 = covers.cover300;
            album.cover640 = covers.cover640;
            album.colorDark = covers.
            album.colorLight = covers.
            album.colorRaw = covers.colorRaw;
        }

        // Tracks: data.albumUnion.tracksV2.
            items[]
        var items =
            albumNode &&
                albumNode.tracksV2 &&
                Array.isArray(albumNode.
                ? albumNode.tracksV2.items
                : [];

        items.forEach(function (item) {
            if (!item || !item.track) return;

            var t = item.track;

            var artists = '';
            if (t.artists && Array.isArray(t.
                artists.items)) {
                artists = t.artists.items
                    .map(function (a) {
                        return a.profile && 
                            a.profile.name ? 
                    })
                    .filter(function (n) { 
                    .join(', ');
            }

            var albumName = '';
            if (t.albumOfTrack && t.
                albumOfTrack.name) {
                albumName = t.albumOfTrack.
            }

            var ms = (
                t.duration &&
                typeof t.duration.
                    totalMilliseconds === 
            ) ? t.duration.totalMilliseconds 
                : null;

            var discNumber = t.discNumber 
                !== undefined ? t.discNumber 
            var trackNumber = t.trackNumber 
                !== undefined ? t.

            var isPlayable = (t.
                playability && typeof t.
                playability.playable === 
                ? String(t.playability.
                : '';

            var playReason = (t.
                playability && t.playability.
                ? t.playability.reason
                : '';

            // Explicit/content rating
            var explicit = '';
            if (t.contentRating && t.
                contentRating.label) {
                explicit = t.contentRating.
                    label; // e.g. 
            }

            // linked/relinked URI
            var relinkedUri = '';
            if (t.relinkingInformation &&
                t.relinkingInformation.
                    linkedTrack &&
                t.relinkingInformation.
                    linkedTrack.uri) {
                relinkedUri = t.
                    relinkingInformation.
            }

            var playcount = t.playcount || 
            colorDark.hex;
            colorLight.hex;
        items)) {
            length;
            available
                'number') {
                    totalCount;
        'number') {
                '';
                ALBUM
                '';
                (albumNode);
                (albumNode);
                discCount;
                    '';
                    '';
                colorDark;
                colorLight;
                    tracksV2.items)
                            a.profile.name : 
                            '';
                        return n; })
                    name;
                    'number'
                : '';
                trackNumber : '';
                'boolean')
                    playable)
                reason)
                    "EXPLICIT" or "NONE"
                    linkedTrack.uri;
                '';
            var uri = t.uri || '';

            tracks.push({
                discNumber: discNumber,
                trackNumber: trackNumber,
                title: t.name || '',
                artists: artists,
                albumName: albumName,
                duration: msToMinSec(ms),
                durationMs: ms !== null ? ms 
                    : '',
                uri: uri,
                relinkedUri: relinkedUri,
                isPlayable: isPlayable,
                playReason: playReason,
                playcount: playcount,
                explicit: explicit
            });
        });
    } catch (e) {
        rawAlbumJson = 'Error parsing 
            response JSON: ' + e.message;
    }

    return {
        album: album,
        tracks: tracks,
        rawAlbumJson: rawAlbumJson
    };
}

pm.visualizer.set(template, 
    constructVisualizerPayload());
```

------

How to use this for tagging:

1. In your `getAlbum` request, open **Tests**, paste the script, and send the request.
2. In the response, go to **Visualize**:
   - Use the **Album tags** table to correct `ALBUM`, `ALBUMARTIST`, `YEAR`, `LABEL`, etc.
   - Use the **Track tags** table to correct `TITLE`, `ARTIST`, `TRACKNUMBER`, `DISCNUMBER`, and optionally store Spotify URIs / playcount in custom tags.
   - Use the **Raw album JSON** block when you want to dig out anything else that’s not already mapped.

If your album response also includes things like genres, ISRCs, or extra identifiers that you want mapped into specific tag frames (e.g., `TXXX/SPOTIFY_TRACK_URI`, `TXXX/SPOTIFY_ALBUM_ID`), tell me exactly which extra fields you care about and how you want them named, and I’ll extend this sheet to include those too.