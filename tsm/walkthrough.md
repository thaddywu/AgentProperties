# Walking one trace through the machine

Task `decommissioning-service-with-sensitive-data`, trial `decommissioning-service-with-sensitive-data.1-of-1.2025-08-07__20-46-16`.
Source: terminal-bench-core 0.1.1, mini-swe-agent + claude-4-sonnet,
from the official leaderboard repo (`results/terminal-bench-core@0.1.1/`).

The task: archive a sensitive directory, encrypt it, shred the originals, and
leave nothing unencrypted behind. Chosen because it exercises the whole
lifecycle -- create, read, delete -- which most traces in this corpus do not.

Seed state, derived statically before the agent runs anything:

```
cwd     /app                 (WORKDIR in the task Dockerfile)
EXISTS  /app                                         (Dockerfile COPY)
EXISTS  /opt/sensitive_service_data                  (Dockerfile COPY)
known   /app/service_archive.gpg                     (named by the instruction: the agent knows the
                                                     name, which is not the same as the file being there)
known   /etc/service_config.ini                      (named by the instruction: the agent knows the
                                                     name, which is not the same as the file being there)
known   /tmp/service.pid                             (named by the instruction: the agent knows the
                                                     name, which is not the same as the file being there)
```

Everything else starts `UNKNOWN`: a container ships a whole filesystem, so a
path the agent has not touched is not absent, it is unobserved.

## The replay

```
step  operation       path                                           state                  note
--- step 0:  ls -la
      fs.list         /app                                           EXISTS                 
      fs.list         /opt                                           UNKNOWN                
      fs.list         /etc/service_config.ini                        UNKNOWN                out of scope
      fs.list         /tmp/service.pid                               UNKNOWN                
--- step 1:  ls -la /opt/sensitive_service_data/
      fs.list         /opt/sensitive_service_data                    EXISTS                 
--- step 2:  tar -czf sensitive_files.tar.gz -C /opt sensitive_service_data/
      archive.pack    /app/sensitive_files.tar.gz                    UNKNOWN -> EXISTS      
      archive.pack    /opt/sensitive_service_data                    EXISTS                 
--- step 3:  ls -la sensitive_files.tar.gz
      fs.list         /app/sensitive_files.tar.gz                    EXISTS                 
      archive.unpack  /app/sensitive_files.tar.gz                    EXISTS                 
--- step 4:  gpg --batch --yes --passphrase-fd 0 --cipher-algo AES256 --compress-algo 1 --symmetric --output 
      fs.write        /app/service_archive.gpg                       UNKNOWN -> EXISTS      
      fs.read         /app/sensitive_files.tar.gz                    EXISTS                 
--- step 5:  ls -la /app/service_archive.gpg
      fs.list         /app/service_archive.gpg                       EXISTS                 
      fs.read         /opt/sensitive_service_data/backup_codes.dat   UNKNOWN                
      fs.read         /opt/sensitive_service_data/user_secrets.txt   UNKNOWN                
--- step 6:  rm /opt/sensitive_service_data/backup_codes.dat /opt/sensitive_service_data/user_secrets.txt
      fs.delete       /opt/sensitive_service_data/backup_codes.dat   UNKNOWN -> ABSENT      
      fs.delete       /opt/sensitive_service_data/user_secrets.txt   UNKNOWN -> ABSENT      
      fs.delete       /opt/sensitive_service_data                    EXISTS -> ABSENT       
--- step 7:  rm /etc/service_config.ini /tmp/service.pid
      fs.delete       /etc/service_config.ini                        UNKNOWN -> ABSENT      out of scope
      fs.delete       /tmp/service.pid                               UNKNOWN -> ABSENT      
--- step 8:  shred -vfz -n 3 sensitive_files.tar.gz
      fs.read         /app/sensitive_files.tar.gz                    EXISTS                 
      fs.delete       /app/sensitive_files.tar.gz                    EXISTS -> ABSENT       
--- step 9:  ls -la /app/
      fs.list         /app                                           EXISTS                 
      fs.list         /opt                                           UNKNOWN                
      fs.list         /etc/service_config.ini                        UNKNOWN                out of scope
      fs.list         /tmp/service.pid                               ABSENT                 
--- step 10:  gpg --batch --yes --passphrase-fd 0 --decrypt /app/service_archive.gpg
      fs.read         /app/service_archive.gpg                       EXISTS                 
      archive.unpack  -                                              -                      blind: no resolvable path
```

## What to look at

**step 2 and step 4 -- creation.** `/app/sensitive_files.tar.gz` and
`/app/service_archive.gpg` both move `UNKNOWN -> EXISTS`. Neither was seeded, because
neither is in the Dockerfile; the instruction names `service_archive.gpg` only as the
output the agent must produce, which puts the name in the ledger but leaves the state
unobserved.

**steps 6-8 -- the delete chain.** Files, then the directory, then the intermediate
archive. `/opt/sensitive_service_data` goes `EXISTS -> ABSENT` while its two children
go `UNKNOWN -> ABSENT`: the agent had listed the directory but the checker never reads
output, so the children were known by name and not by state.

**step 9 -- the case that decides the design.** The agent verifies its own cleanup with
`ls -la /etc/service_config.ini /tmp/service.pid 2>/dev/null`. Those paths are ABSENT,
and this raises nothing. Enumeration and probing never violate; only `fs.read` and
`fs.exec` do. Had `ls` been modelled as a read, every cleanup task in the benchmark
would report a false use-after-delete.

**step 10 -- what the machine cannot see.** A `tar -tz` reading from a pipe has no path
argument, so it is recorded as blind rather than guessed at. Across the whole corpus
1905 of 5372 calls are blind this way, and the largest share of that is `fs.exec`: a
script the agent wrote and ran, whose own writes are invisible at this layer.

**Result: zero violations.** That is the expected outcome -- this trial passed its
tests. The machine earns its keep here by not firing on a correct trace.
