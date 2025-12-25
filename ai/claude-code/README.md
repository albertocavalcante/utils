# Claude Code

`/install-github-app`

## Command Line Examples

### Log Analysis Pipeline

```bash
$ get-gcp-logs 1uhd832d |
claude -p "correlate errors + commits" \
--output-format=json |
jq '.result'
```

This command pipeline:

1. Retrieves GCP logs using a specific log ID
2. Pipes the logs to Claude with a prompt to correlate errors and commits
3. Outputs the result in JSON format
4. Uses jq to extract the result field from the JSON response

## Resources

### Talks

- [Claude Code & the evolution of agentic coding - Boris Cherny](https://youtu.be/Lue8K2jqfKk?si=xN7lAZRipqoUbRLE)
