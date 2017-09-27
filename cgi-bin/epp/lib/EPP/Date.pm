package EPP::Date;

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



use strict;
use warnings;

use Time::HiRes 'gettimeofday';
use POSIX 'strftime';

BEGIN {
	use Exporter ();
	our ($VERSION, @ISA, @EXPORT, @EXPORT_OK, %EXPORT_TAGS);

	$VERSION = do { my @r = (q$Revision: 1.01 $ =~ /\d+/g); sprintf "%d."."%02d" x $#r, @r};
	@ISA = qw(Exporter);
	@EXPORT = qw();
	@EXPORT_OK = qw(date_for_svtrid date_epp microsecond);
	%EXPORT_TAGS = ('all' => \@EXPORT_OK);
}

our @EXPORT_OK;

sub date_for_svtrid {
	my $ts = gettimeofday;
	$ts = sprintf("%.5f", $ts);
	my ($sec,$usec) = split(/\./, $ts);
	my $s = strftime("%Y%m%d%H%M%S", localtime($ts));
	$s .= $usec;

	return $s;
}

sub date_epp {
	my $ts = gettimeofday;
	$ts = sprintf("%.5f", $ts);
	my ($sec,$usec) = split(/\./, $ts);
	my $s = strftime("%Y-%m-%dT%H:%M:%S", localtime($ts));
	$usec = 0 unless($usec);
	$usec = int($usec / 100000);
	$s .= '.' . $usec . 'Z';

	return $s;
}

sub microsecond {
	my $ts = gettimeofday;
	$ts = sprintf("%.5f", $ts);
	my ($sec,$usec) = split(/\./, $ts);
	my $s = strftime("%Y-%m-%dT%H:%M:%S", localtime($ts));
	$s .= '.' . $usec;

	return $s;
}

1;