#Icinga Plugins

This is repository for various Icinga (and Nagios) plugins which we developed.

##Plugins

### check_zones_in_sync

Check if zones are in sync on multiple DNS servers really fast.

Plugin makes query for every zone in given text file to given DNS servers,
retrieve SOA record and compare serial from it.

Works similar to [checkexpire plugin](http://exchange.nagios.org/directory/Plugins/Network-Protocols/DNS/checkexpire/details) but much faster.

check_zones_in_sync is tested on ruby 1.9.3 and requires [rubydns](https://github.com/ioquatix/rubydns) gem
    gem install rubydns

#### Usage

check_zones_in_sync -s 1.2.3.4,2.2.3.4 -f /etc/icinga/zonelist.txt

### Other plugins

* check_smtp_blacklist - check if your host is on blacklist
* check_chef_client - check if chef-client run failed
* check_postfix_queues - check status of postfix queues

##LICENSE

All plugins are released under MIT license.

