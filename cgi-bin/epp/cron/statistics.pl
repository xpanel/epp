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



# run statistics.pl hourly

use lib '/var/www/cgi-bin/epp/lib';
use strict;
use warnings;
use EPP::Config();
use DBI;
use vars qw(%c $dbh);
*c = \%EPP::Config::c;
$dbh = DBI->connect("DBI:mysql:$c{'mysql_database'}:$c{'mysql_host'}:$c{'mysql_port'}","$c{'mysql_username'}","$c{'mysql_password'}") or die "$DBI::errstr";


my $curdate_id = $dbh->selectrow_array("SELECT `id` FROM `statistics` WHERE `date` = CURDATE()");

if (!$curdate_id) {
	$dbh->do("INSERT IGNORE INTO `statistics` (`date`) VALUES(CURDATE())") or die $dbh->errstr;
}

my $total_domains = $dbh->selectrow_array("SELECT COUNT(`id`) AS `total_domains` FROM `domain`");

$dbh->do("UPDATE `statistics` SET `total_domains` = '$total_domains' WHERE `date` = CURDATE()") or die $dbh->errstr;


# End.