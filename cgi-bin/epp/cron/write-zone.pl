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
use vars qw(%c $dbh);
*c = \%EPP::Config::c;
$dbh = DBI->connect("DBI:mysql:$c{'mysql_database'}:$c{'mysql_host'}:$c{'mysql_port'}","$c{'mysql_username'}","$c{'mysql_password'}") or die "$DBI::errstr";

my $restart = 0;
my $sth = $dbh->prepare("SELECT `id`,`tld` FROM `domain_tld`");
$sth->execute();

my $timestamp = time;
my $ns1 = 'ns1.xpanel.net';
my $ns2 = 'ns2.xpanel.net';

while (my ($id,$tld) = $sth->fetchrow_array) {
	my $tldRE = $tld;
	$tldRE =~ s/\./\\./g;
	open(OUT, '>', "/var/named/named${tld}.zone") or print "Unable to open file '/var/named/named${tld}.zone'. $! \n";
		print OUT qq|\$TTL\t1H\n\@\tIN\tSOA\t${ns1}.\tpostmaster${tld}. (\n\t$timestamp\n\t3H\n\t1H\n\t1W\n\t1D\n\t)\n\n|;
		print OUT qq|\@\t1H\tIN\tNS\t${ns1}.\n|;
		print OUT qq|\@\t1H\tIN\tNS\t${ns2}.\n|;
		print OUT qq|\n|;

		# Select all the hosts
		my $sth2 = $dbh->prepare("SELECT DISTINCT
									 `domain`.`id`,
									 `domain`.`name`,
									 `host`.`name`
									FROM
									 `domain`,
									 `domain_host_map`,
									 `host`
									LEFT JOIN `host_addr` ON (
									 `host_addr`.`host_id` = `host`.`id`
									)
									WHERE
									 `domain`.`tldid` = '${id}'
									AND `domain`.`id` = `domain_host_map`.`domain_id`
									AND `domain_host_map`.`host_id` = `host`.`id`
									AND (
									 `host`.`domain_id` IS NULL
									 OR `host_addr`.`addr` IS NOT NULL
									)
									AND (
									 `domain`.`exdate` > NOW()
									 OR `rgpstatus` = 'pendingRestore'
									)
									ORDER BY
									 `domain`.`name`");
		$sth2->execute();

		# clientHold, serverHold
		# DNS delegation information MUST NOT be published for the object.
		# aici mai trebuie de adaugat daca status este hold apoi next
		while (my ($did,$dname,$hname) = $sth2->fetchrow_array) {
			my ($status_id) = $dbh->selectrow_array("SELECT `id` FROM `domain_status` WHERE `domain_id` = '$did' AND `status` LIKE '%Hold' LIMIT 1");
			next if ($status_id);
			$dname .= '.';
			$dname =~ s/\.$tldRE\.$//i;
			$dname = '@' if ($dname eq "$tld.");

			$hname .= '.';
			$hname =~ s/$tldRE\.$//i;
			print OUT "$dname\tIN\tNS\t$hname\n";
		}
		$sth2->finish;

		# Select the A and AAAA records
		$sth2 = $dbh->prepare("SELECT `host`.`name`,`host`.`domain_id`,`host_addr`.`ip`,`host_addr`.`addr` 
				FROM `domain`,`host`,`host_addr` 
				WHERE `domain`.`tldid` = '${id}'
				AND `domain`.`id` = `host`.`domain_id`
				AND `host`.`id` = `host_addr`.`host_id`
				AND (`domain`.`exdate` > NOW() OR `rgpstatus` = 'pendingRestore')
				ORDER BY `host`.`name`");
		$sth2->execute();
		while (my ($hname,$did,$type,$addr) = $sth2->fetchrow_array) {
			my ($status_id) = $dbh->selectrow_array("SELECT `id` FROM `domain_status` WHERE `domain_id` = '$did' AND `status` LIKE '%Hold' LIMIT 1");
			next if ($status_id);
			$hname .= '.';
			$hname =~ s/$tldRE\.$//i;
			$hname = '@' if ($hname eq "$tld.");

			if ($type eq 'v4') {
				print OUT "$hname\tIN\tA\t$addr\n";
			}
			else {
				print OUT "$hname\tIN\tAAAA\t$addr\n";
			}
		}
		$sth2->finish;

		print OUT "\n; EOF\n";
	close(OUT);
}
$sth->finish;

system("systemctl reload named.service") == 0 or print "Failed to reload named. $! \n";