#!/usr/bin/ruby

# Copyright (c) 2010 IglooNET, s.r.o.   http://www.igloonet.cz/
#         
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#           
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.
#   
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

require 'singleton'
require 'optparse'
require 'open3'

class PostfixQueuesChecker
  include Singleton

  def initialize

    @options = {}
    @warning_level = {}
    @critical_level = {}

    @options[:queues] = [ :incoming, :active, :deferred, :corrupt, :hold ]

    @options[:spooldir] = `/usr/sbin/postconf -h queue_directory 2>/dev/null`.chomp

    if @options[:spooldir].empty?
      @options[:spooldir] = "/var/spool/postfix"
    end

    begin
      get_options
    rescue ArgumentError => e
      puts e.message; exit(1)
    end

    @options[:queues].each do |queue|
      unless @warning_level.has_key? queue and @critical_level.has_key? queue
        puts "Some levels for queue #{queue} are not set!"
        exit 2
      end
    end

  end

  def get_options
    OptionParser.new do |opts|
      opts.banner = "Usage: #{File.basename $0} [options]"
      opts.separator ""
      opts.separator "Specific options:"

      opts.on('-s', '--spooldir PATH', 'Path to spool directory') do |path|
        @options[:spooldir] = path
      end

      opts.on('-q', '--queues x,y,z', Array, 'List of queues for processing') do |list|

        list.collect! { |item| item.to_sym }

        accepted = @options[:queues] & list

        unless list == accepted
          invalid = list - accepted

          puts "Some queues' names are invalid!"
          puts invalid

          exit 2
        end

        @options[:queues] = accepted
      end

      opts.on('-w', '--warning N', Integer, 'Warning count of mails in any queue') do |count|
        @options[:queues].each do |queue|
          @warning_level[queue] = count
        end
      end

      opts.on('-c', '--critical N', Integer, 'Critical count of mails in any queue') do |count|
        @options[:queues].each do |queue|
          @critical_level[queue] = count
        end
      end

      opts.on('--wincoming N', Integer, 'Count for incoming queue warning') do |count|
        @warning_level[:incoming] = count
      end

      opts.on('--cincoming N', Integer, 'Count for incoming queue critical') do |count|
        @critical_level[:incoming] = count
      end

      opts.on('--wactive N', Integer, 'Count for active queue warning') do |count|
        @warning_level[:active] = count
      end

      opts.on('--cactive N', Integer, 'Count for active queue critical') do |count|
        @critical_level[:active] = count
      end

      opts.on('--wdeferred N', Integer, 'Count for deferred queue warning') do |count|
        @warning_level[:deferred] = count
      end

      opts.on('--cdeferred N', Integer, 'Count for deferred queue critical') do |count|
        @critical_level[:deferred] = count
      end

      opts.on('--wcorrupt N', Integer, 'Count for corrupt queue warning') do |count|
        @warning_level[:corrupt] = count
      end

      opts.on('--ccorrupt N', Integer, 'Count for corrupt queue critical') do |count|
        @critical_level[:corrupt] = count
      end

      opts.on('--whold N', Integer, 'Count for hold queue warning') do |count|
        @warning_level[:hold] = count
      end

      opts.on('--chold N', Integer, 'Count for hold queue critical') do |count|
        @critical_level[:hold] = count
      end

      opts.on('-h', '--help', 'Show this message and exit') { puts opts; exit}

    end.parse!
  end

  def get_queue_count( queue_name )
    count = 0

    begin
      output = nil

      Open3.popen3("find #{@options[:spooldir]}/#{queue_name}/. ! -name . ! -name '?' -print") do |stdin, stdout, stderr|

        output = stdout.read

        raise "Error while counting mails! - #{stderr.read}" unless $? == 0
      end

      Open3.popen3('wc -l') do |stdin, stdout, stderr|

        stdin.print output
        stdin.close

        count = stdout.read.to_i
        raise "Error while counting mails! - #{stderr.read}" unless $? == 0
      end


    rescue Exception => e
      print e
      exit 2
    end

    return count
  end

  def run
    output = ''
    exit_code = 0

    @options[:queues].each do |queue|
      mail_count = self.get_queue_count(queue)
      state = ''

      if mail_count >= @critical_level[queue]
        state = 'CRITICAL'

        exit_code = 2 if exit_code < 2
      elsif mail_count >= @warning_level[queue]
        state = 'WARNING'

        exit_code = 1 if exit_code < 1
      else
        state = 'OK'
      end

      output << "Queue #{queue}, Mail count: #{mail_count}, State: #{state}\n"

    end

    print output
    exit exit_code

  end

end

PostfixQueuesChecker.instance.run

