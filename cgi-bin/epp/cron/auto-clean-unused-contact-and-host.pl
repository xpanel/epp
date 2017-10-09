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
#	(c) Copyright 2017 XPanel Ltd.
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
use EPP::Date qw(:all);
use vars qw(%c $dbh @list);
*c = \%EPP::Config::c;
$dbh = DBI->connect("DBI:mysql:$c{'mysql_database'}:$c{'mysql_host'}:$c{'mysql_port'}","$c{'mysql_username'}","$c{'mysql_password'}") or die "$DBI::errstr";

open(LOGFILE, '>>', '/var/log/epp/clean.log') or print "Failed to open file '/var/log/epp/clean.log'. $! \n";

my $sth = $dbh->prepare("SELECT `h`.`id`,`h`.`name` FROM `host` AS `h`
	LEFT JOIN `domain_host_map` AS `m` ON `h`.`id` = `m`.`host_id`
	WHERE `m`.`host_id` IS NULL AND `h`.`domain_id` IS NULL AND `h`.`crdate` < (NOW() - INTERVAL 1 MONTH)") or die $dbh->errst;
$sth->execute() or die $sth->errstr;
@list = ();
my $i = 0;
while (my $f = $sth->fetchrow_hashref) {
	push(@{$list[$i++/1000]},$f);
}
$sth->finish;
for my $f (@list) {
	my @id = map {$_->{id}} @$f;
	$dbh->do("DELETE FROM `host_status` WHERE `host_id` IN ('".join("','",@id)."')") or die $dbh->errstr;
	$dbh->do("DELETE FROM `host_addr` WHERE `host_id` IN ('".join("','",@id)."')") or die $dbh->errstr;
	$dbh->do("DELETE FROM `host` WHERE `id` IN ('".join("','",@id)."')") or die $dbh->errstr;
	my @log = map {"Delete HOST-".$_->{id}." (".$_->{name}.")"} @$f;
	print LOGFILE join("\n",@log)."\n";
}

$sth = $dbh->prepare("SELECT `c`.`id`,`c`.`identifier` FROM `contact` AS `c`
	LEFT JOIN `domain_contact_map` AS `m` ON `c`.`id` = `m`.`contact_id`
	LEFT JOIN `domain` AS `d` ON `c`.`id` = `d`.`registrant`
	WHERE
	`m`.`contact_id` IS NULL AND
	`d`.`registrant` IS NULL AND
	`c`.`crdate` < (NOW() - INTERVAL 1 MONTH)") or die $dbh->errst;
$sth->execute() or die $sth->errstr;
@list = ();
$i = 0;
while (my $f = $sth->fetchrow_hashref) {
	push(@{$list[$i++/1000]},$f);
}
$sth->finish;
for my $f (@list) {
	my @id = map {$_->{id}} @$f;
	$dbh->do("DELETE FROM `contact_status` WHERE `contact_id` IN ('".join("','",@id)."')") or die $dbh->errstr;
	$dbh->do("DELETE FROM `contact_postalInfo` WHERE `contact_id` IN ('".join("','",@id)."')") or die $dbh->errstr;
	$dbh->do("DELETE FROM `contact_authInfo` WHERE `contact_id` IN ('".join("','",@id)."')") or die $dbh->errstr;
	$dbh->do("DELETE FROM `contact` WHERE `id` IN ('".join("','",@id)."')") or die $dbh->errstr;
	my @log = map {"Delete CONTACT-".$_->{id}." (".$_->{identifier}.")"} @$f;
	print LOGFILE join("\n",@log)."\n";
}
close LOGFILE;