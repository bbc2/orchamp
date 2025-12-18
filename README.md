# Orchamp

## ☣️ Hazardous material

This project is still in its infancy. It is not finished and it may even turn out to be
stupid. For example, many questions haven't been answered: Is it useful? Is it the right
approach for the problem? Do the technology choices make sense?

## Introduction

**Orchamp** is a championship analyzer that uses constraint programming to explore all possible outcomes in the league.

## Usage

### Web application

Go to the web application, select a league (year, division, phase), and see current standings.

### CLI

To analyze possible future positions of a given team in the championship:

```bash
orchamp \
  --rules tests/orchamp/cli/data/rules.json \
  --state <(orchamp-get parse tests/orchamp_get/data/standings.html) \
  analyze-team --team team_b
```

This outputs JSON in the following form:

```json
{
  "team_id": "team_b",
  "team_name": "Team B",
  "best_position": 1,
  "worst_position": 5,
  "best_scenario": {
    ...
  },
  "worst_scenario": {
    ...
  }
}
```
