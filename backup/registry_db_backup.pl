#!/usr/bin/perl

###############################################################################
#
#	-------------------------
#			XPanel EPP Server
#		-------------------------
#
#	Version: 1.0.0
#	Web Site: http://www.xpanel.com/
#
#	(c) Copyright 2014 XPanel Ltd.
#
# *  XPanel Ltd. licenses this file to You under the Apache License, Version 2.0
# *  (the "License"); you may not use this file except in compliance with
# *  the License.  You may obtain a copy of the License at
# *
# *      http://www.apache.org/licenses/LICENSE-2.0
# *
# *  Unless required by applicable law or agreed to in writing, software
# *  distributed under the License is distributed on an "AS IS" BASIS,
# *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#
###############################################################################



use lib '/var/www/cgi-bin/epp/lib';
use strict;
use warnings;
use EPP::Config();
use DBI;
use POSIX 'strftime';
use vars qw(%c $dbh);
*c = \%EPP::Config::c;





my $current_date = strftime("%Y-%m-%d-%H", localtime);

my ($year,$month,$day,$hour) = split(/\-/, $current_date);

if (!-d "/usr/local/registry/backups/$year") {
	mkdir("/usr/local/registry/backups/$year") or die "$!\n";
}

if (!-d "/usr/local/registry/backups/$year/$month") {
	mkdir("/usr/local/registry/backups/$year/$month") or die "$!\n";
}

if (!-d "/usr/local/registry/backups/$year/$month/$day") {
	mkdir("/usr/local/registry/backups/$year/$month/$day") or die "$!\n";
}

system("mysqldump -h\"$c{'mysql_host'}\" -P\"$c{'mysql_port'}\" -u\"$c{'mysql_username'}\" -p\"$c{'mysql_password'}\" \"$c{'mysql_database'}\" > \"EPP_Registry_DB_$current_date.sql\"");
my $file = 'EPP_Registry_DB_'.$current_date.'.sql.bz2';
system("pbzip2 EPP_Registry_DB_$current_date.sql");
unlink("EPP_Registry_DB_$current_date.sql");
system("mv $file /usr/local/registry/backups/$year/$month/$day/");

system("mysqldump -h\"$c{'mysql_host'}\" -P\"$c{'mysql_port'}\" -u\"$c{'mysql_username'}\" -p\"$c{'mysql_password'}\" \"registryTransaction\" > \"EPP_Registry_Transaction_$current_date.sql\"");
my $fileTransaction = 'EPP_Registry_Transaction_'.$current_date.'.sql.bz2';
system("pbzip2 EPP_Registry_Transaction_$current_date.sql");
unlink("EPP_Registry_Transaction_$current_date.sql");
system("mv $fileTransaction /usr/local/registry/backups/$year/$month/$day/");


# End.