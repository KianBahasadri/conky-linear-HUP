So essentially, I'm just doing this to give myself some kind of structure. I hope that by creating goals each day that I like and want to achieve, I will spend my days working towards those goals.

For now I've set this up as recurring tasks in linear, however I have created a conky setup to display linear Todo and In Progress tasks over my desktop wallpaper as a widget/constant reminder.

This repo contains a Conky-based desktop overlay for Linear tasks: a Python script fetches active Linear issues and recently completed issues from the Linear GraphQL API, writes a local card cache, and a Lua/Cairo Conky renderer displays those tasks as horizontal pills across the top of each monitor. Unfinished tasks are colored based on whether they are due today, recently completed tasks are shown in green, and helper scripts start or stop matching overlay instances across all detected monitors.
