# DS5220 - Data Project 3: Data Ingestion Pipeline and Integration API

This project implements a data ingestion pipeline and Chalice API that ingests, processes, and displays concurrent player count data for 3 lifestyle simulation games on Steam - The Sims 4, Stardew Valley, and Heartopia.

## Motivation

The player count data was sourced from SteamDB, a database that tracks many characteristics of the entire catalog of Steam, a gaming platform. I chose to look at these 3 games, because I play Sims 4 sometimes, and being that it has been around for over a decade (released in 2014), it has become a household name and goes through fluctuations in popularity. I wanted to see how it fared in comparison to 2 other games, one similar in age (Stardew Valley, which was released 2 years after Sims 4) and one that was released recently (Heartopia, which was released in early 2026). I also happen to like more slow paced and casual games, so this data was just interesting for me.

## Sampling + Storage Schema

The data is sampled every 10 minutes, as that is the frequency at which player counts for games that are ranked below the top 1,000 games are updated. All 3 of the games are ranked above 1,000 (these are updated every 5 minutes), however game popularity is quick to fluctuate, so I chose to go with the slower interval to avoid duplicate values, should any of the games drop in rank.

The DynamoDB database stores 3 values for each object stored:
- `GameName`: the title of the game
- `Timestamp`: the UTC time at which the data point was ingested
- `Count`: the number of players concurrently playing the game

### API Resources

The API has 3 resources:
- `/current`: returns the most recent player count values for all 3 games
- `/trend`: returns the change in player count as compared to an hour prior
- `/plot`: returns a plot that displays the trend in player counts for each game over the past 24 hours from the present

### Extension

I had wanted to extend the plot resource to allow for a parameter that adjusted the time frame of the plot to allow users to look at trends over longer or shorter periods of time, but unfortunately, I couldn't get it to work properly. 
