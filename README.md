# Garmin Indoor Run Distance "Fix"

Quick hack to correct the distances when you record an indoor (track/treadmill) workout where you know the exact distances of each rep. 

## Usage
1. Find the target activity on the Garmin Connect website. Click the gear in the top right corner and "Export to TCX". The file should be named `activity_xxx.tcx`
2. Create a "laps" text file, eg. `laps_xxx.txt` which specifies the correct distances of each rep in miles, one rep per line. For example, a workout with a 1 mile warm, 4x400, 4x200, 1 mile cooldown would look like this:
```
1.0
0.25
0.25
0.25
0.25
0.125
0.125
0.125
0.125
1.0
```
3. Run `python fix.py activity_xxx.tcx laps_xxx.txt`. This will create a new `activity_xxx-fixed.tcx` file in the same directory. 
4. On the strava website, click the plus in the top right corner, then "Upload Activity" and upload the fixed tcx file. *NOTE*: if the original activity was auto-uploaded to Strava, you'll need to delete it first, otherwise Strava will complain it's a duplicate activity. If something goes wrong, you can always downloda the original FIT file from the Garmin website and reupload it to Strava without any consequence. 

## Notes

For now, this works with the TCX activity format, because it's an easy to parse XML format. However, it's a bit of a clunky format and is ambiguous about eg. pause periods, so Strava's parsing doesn't recognize them (if you upload the original TCX file directly from Garmin, Strava considers pauses as workout data at 0 speed, which throws off total active time and pace stats). Given the correct distances, this script stretches out the data points from each rep to fit those distances, and it removes pause periods so that Strava won't get confused. In other words, the watch is mainly just providing your time for each lap. Assuming you provide the correct distances, the pacing should be exactly correct as well.

## Sample

`activities/` contains a sample input (original activity, lap file) and output (corrected activity).

```
❯ python fix.py activities/activity_10128119638.tcx activities/laps_10128119638.txt
lap 1	::	1.382m -> 1.743km (total=0.000km)	dist=1.083	time=366.0	split=5:37/mi
lap 2	::	0.174m -> 0.201km (total=1.743km)	dist=0.125	time=43.0	split=5:44/mi
lap 3	::	0.166m -> 0.201km (total=1.944km)	dist=0.125	time=39.0	split=5:12/mi
lap 4	::	0.169m -> 0.201km (total=2.145km)	dist=0.125	time=42.0	split=5:35/mi
lap 5	::	0.155m -> 0.201km (total=2.346km)	dist=0.125	time=36.0	split=4:47/mi
lap 6	::	1.377m -> 1.743km (total=2.548km)	dist=1.083	time=361.0	split=5:33/mi
lap 7	::	0.147m -> 0.201km (total=4.291km)	dist=0.125	time=41.0	split=5:28/mi
lap 8	::	0.145m -> 0.201km (total=4.492km)	dist=0.125	time=35.0	split=4:40/mi
lap 9	::	0.152m -> 0.201km (total=4.693km)	dist=0.125	time=35.0	split=4:40/mi
lap 10	::	0.154m -> 0.201km (total=4.894km)	dist=0.125	time=25.0	split=3:20/mi
lap 11	::	0.970m -> 1.127km (total=5.095km)	dist=0.700	time=299.0	split=7:07/mi
-> Total	km=6.222	miles=3.866	split=5:41/mi
```
